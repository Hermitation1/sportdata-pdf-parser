import json
import logging
import os
import time

logger = logging.getLogger("pdf-parser")

from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode,
    RapidOcrOptions
)
from docling.datamodel.base_models import InputFormat
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
from docling.document_converter import PdfFormatOption

from app.models import ContestFront
from openai import OpenAI


# Пороги для LLM-экстракции (в символах).
_HEADER_CHARS = 3000
_SMALL_DOC_CHARS = 20000
_CHUNK_SIZE = 6000

_converter: DocumentConverter | None = None
_client: OpenAI | None = None


def _get_converter() -> DocumentConverter:
    global _converter
    if _converter is None:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.images_scale = 3.0

        pipeline_options.accelerator_options = AcceleratorOptions(
            device=AcceleratorDevice.CUDA,
            num_threads=4,
        )

        pipeline_options.ocr_options = RapidOcrOptions(
            lang=["latin"],  # cls-модель для кириллицы (rec — eslav/rec.onnx)
            force_full_page_ocr=True,
            det_model_path="paddleocr_models/detection/v5/det.onnx",
            rec_model_path="paddleocr_models/languages/eslav/rec.onnx",
            rec_keys_path="paddleocr_models/languages/eslav/dict.txt",
            rapidocr_params={
                "EngineConfig.onnxruntime.use_cuda": os.getenv("RAPIDOCR_DEVICE") == "cuda",
            },
        )

        pipeline_options.table_structure_options = TableStructureOptions(
            mode=TableFormerMode.ACCURATE,
            do_cell_matching=True,
        )
        pipeline_options.generate_parsed_pages = True

        _converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )

    return _converter


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        _client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return _client


def process_pdf(file_path: str, task_id: str) -> None:
    t0 = time.time()
    converter = _get_converter()
    t1 = time.time()
    result = converter.convert(file_path)
    t2 = time.time()

    markdown_text = result.document.export_to_markdown()
    output_path = f"files/{task_id}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown_text)
    logger.info(f"[TIMING] init: {t1-t0:.1f}s, convert: {t2-t1:.1f}s, total: {time.time()-t0:.1f}s")



def extract_contest_json(markdown_text: str) -> dict:
    """Многопроходное извлечение: заголовок + каждый протокол отдельно."""
    client = _get_client()

    # ── Проход 1: заголовок + регионы + судьи ──
    header_text = markdown_text[:_HEADER_CHARS]
    judge_section = ""
    ji = markdown_text.find("СПОРТИВНЫХ СУДЕЙ")
    if ji > 0:
        judge_section = "\n\n" + markdown_text[ji:ji + _HEADER_CHARS]
    region_section = ""
    ri = markdown_text.find("СПРАВКА О КОЛИЧЕСТВЕ")
    if ri > 0:
        region_section = "\n\n" + markdown_text[ri:ri + _HEADER_CHARS]

    header_prompt = (
        "Извлеки из текста заголовочные данные соревнования:\n"
        "- beginning: ПЕРВАЯ дата диапазона (dd.mm.yyyy), из «28.01-02.02.2026» → «28.01.2026»\n"
        "- ending: ПОСЛЕДНЯЯ дата диапазона, из «28.01-02.02.2026» → «02.02.2026»\n"
        "- ekp: 16-значное число в начале документа (может быть после «ЕКП», «EKI», или отдельно)\n"
        "- title, city, location (из заголовка до таблиц, НЕ из названий колонок)\n"
        "- subjectTitle: субъект РФ проведения (из заголовка до таблиц)\n"
        "- sportTitle: вид спорта (из заголовка до таблиц)\n"
        "- totalSubjects: список субъектов-участников из таблицы\n"
        "- судьи: judgeTotal, nonresidentJudge, mc,vrc,fc,sc,tc,bc,dc\n"
        "Верни ТОЛЬКО JSON (без пояснений) в формате:\n"
        '{"ekp":"","title":"","city":"","location":"",'
        '"subjectTitle":"","sportTitle":"","beginning":"","ending":"",'
        '"totalSubjects":[],"participantTotal":0,"boyTotal":0,"girlTotal":0,'
        '"br":0,"yn3":0,"yn2":0,"yn1":0,"r3":0,"r2":0,"r1":0,"kms":0,"ms":0,"msmk":0,"zms":0,"gr":0,'
        '"judgeTotal":0,"nonresidentJudge":0,"mc":0,"vrc":0,"fc":0,"sc":0,"tc":0,"bc":0,"dc":0,'
        '"sports":[]}\n'
        f"Текст:\n{header_text}{region_section}{judge_section}"
    )
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": header_prompt}],
                response_format={"type": "json_object"},
                reasoning_effort="high",
            )
            content = resp.choices[0].message.content
            if not content:
                logger.warning(f"Header attempt {attempt + 1}: empty response")
                continue
            contest = json.loads(content.strip())
            break
        except json.JSONDecodeError as e:
            logger.warning(f"Header attempt {attempt + 1}: broken JSON - {e}")
            if attempt == 2:
                raise
        except Exception as e:
            logger.warning(f"Header attempt {attempt + 1}: {e}")
            if attempt == 2:
                raise

    # ── Проход 2: протоколы — размер батча от размера файла ──
    total_chars = len(markdown_text)
    if total_chars < _SMALL_DOC_CHARS:
        batches = [[markdown_text]]
    else:
        chunk_size = max(_CHUNK_SIZE, total_chars // 10)
        protocols = _split_protocols(markdown_text, chunk_size)
        batches = [[p] for p in protocols]

    sports = []

    for batch_idx, batch in enumerate(batches):
        logger.info(f"Batch {batch_idx + 1}/{len(batches)} ({len(batch)} protocols)")
        batch_text = "\n\n=== ПРОТОКОЛ ===\n\n".join(p for p in batch)
        batch_prompt = (
            "Извлеки из КАЖДОГО протокола дисциплину, возрастную группу и ТОЛЬКО ПРИЗЁРОВ (1, 2, 3 место).\n"
            "Пропускай всех участников ниже 3 места — они не нужны.\n"
            "Верни ТОЛЬКО JSON-объект (без пояснений) с ключом sports в формате:\n"
            '{"sports":[{"disciplineTitle":"название","groupTitle":"группа","groupMinAge":0,"groupMaxAge":0,'
            '"places":[{"place":1,"info":"","newQualificationData":null,'
            '"lastname":"Фамилия","name":"Имя","middleName":"Отчество","birthday":"2007-01-01",'
            '"qualificationCategory":"KMS","schoolTitle":"","schoolSubjectTitle":""}]}]}\n\n'
            f"Протоколы:\n{batch_text}"
        )
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model="deepseek-v4-pro",
                    messages=[{"role": "user", "content": batch_prompt}],
                    response_format={"type": "json_object"},
                    reasoning_effort="low",
                )
                content = resp.choices[0].message.content.strip()
                if content:
                    batch_sports = json.loads(content).get("sports", [])
                    if isinstance(batch_sports, dict):
                        batch_sports = [batch_sports]
                    sports.extend(batch_sports)
                    break
                else:
                    logger.warning(f"Batch {batch_idx + 1}: empty response (attempt {attempt + 1})")
            except json.JSONDecodeError:
                logger.warning(f"Batch {batch_idx + 1}: broken JSON (attempt {attempt + 1})")
                if attempt == 2:
                    raise
            except Exception as e:
                logger.warning(f"Batch {batch_idx + 1}: {e} (attempt {attempt + 1})")
                if attempt == 2:
                    raise

    contest["sports"] = sports
    return ContestFront.model_validate(contest).model_dump(by_alias=True)


def _split_protocols(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Универсальный сплит по ~6K символов (по границам строк)."""
    lines = text.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) > chunk_size and current:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks if chunks else [text[:chunk_size]]

