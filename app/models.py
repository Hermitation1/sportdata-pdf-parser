"""Pydantic-модель для фронтенда — без ID-полей (только извлекаемые из текста)."""

import re
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict, field_validator


_RANK_MAP = {
    "мс": "MS", "mc": "MS", "ms": "MS",
    "кмс": "KMS", "kmc": "KMS", "kms": "KMS",
    "мсмк": "MSMK", "mcmk": "MSMK",
    "змс": "ZMS", "zmc": "ZMS",
    "1": "R1", "2": "R2", "3": "R3",
    "i": "R1", "ii": "R2", "iii": "R3",
    "1юн": "YN1", "2юн": "YN2", "3юн": "YN3",
    "iюн": "YN1", "iiюн": "YN2", "iiiюн": "YN3",
    "б/р": "BR", "бр": "BR", "br": "BR",
    "гр": "GR", "gr": "GR",
}


def _norm_rank(s: str) -> str:
    return _RANK_MAP.get(str(s).strip().lower(), str(s).strip().upper())


class PlaceFront(BaseModel):
    """Участник — только текстовые данные."""
    model_config = ConfigDict(populate_by_name=True)

    place: int | None = Field(None, description="Занятое место")
    info: str = Field("", description="DNS | NM | DQ | ''")
    new_qualification_data: str | None = Field(None, alias="newQualificationData", description="Выполненный разряд")
    condition: str = Field("1", description='"1" — подтверждение, "2" — неподтверждение')
    lastname: str = Field("", description="Фамилия")
    name: str = Field("", description="Имя")
    middle_name: str = Field("", alias="middleName", description="Отчество")
    birthday: str = Field("", description="YYYY-MM-DD")
    qualification_category: str = Field("", alias="qualificationCategory", description="MS | KMS | R1 | ...")
    school_title: str = Field("", alias="schoolTitle", description="Название школы")
    school_subject_title: str = Field("", alias="schoolSubjectTitle", description="Субъект школы")

    @field_validator("place", mode="before")
    @classmethod
    def _coerce_place(cls, v: object) -> int | None:
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @field_validator("qualification_category", "new_qualification_data", mode="before")
    @classmethod
    def _norm_qual(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _norm_rank(str(v))


class SportFront(BaseModel):
    """Дисциплина с участниками."""
    model_config = ConfigDict(populate_by_name=True)

    discipline_title: str = Field("", alias="disciplineTitle", description="Название дисциплины")
    group_title: str = Field("", alias="groupTitle", description="Возрастная группа")
    group_min_age: int = Field(0, alias="groupMinAge")
    group_max_age: int = Field(0, alias="groupMaxAge")
    allowed: list[str] = Field(default_factory=list, description="Допуски")
    standards: list[str] = Field(default_factory=list, description="ФССП")
    places: list[PlaceFront] = Field(default_factory=list)


class ContestFront(BaseModel):
    """Соревнование — плоская структура для формы (без ID)."""
    model_config = ConfigDict(populate_by_name=True)

    ekp: str = Field("", description="16-значный номер ЕКП")
    title: str = Field("", description="Название соревнования")
    sport_title: str = Field("", alias="sportTitle")
    beginning: str = Field("", description="YYYY-MM-DD")
    ending: str = Field("", description="YYYY-MM-DD")
    subject_title: str = Field("", alias="subjectTitle")
    city: str = Field("", description="Город")
    location: str = Field("", description="Спорткомплекс + адрес")

    total_subjects: list[str] = Field(default_factory=list, alias="totalSubjects", description="Названия субъектов-участников")
    participant_total: int = Field(0, alias="participantTotal")
    boy_total: int = Field(0, alias="boyTotal")
    girl_total: int = Field(0, alias="girlTotal")

    br: int = 0
    yn3: int = 0
    yn2: int = 0
    yn1: int = 0
    r3: int = 0
    r2: int = 0
    r1: int = 0
    kms: int = 0
    ms: int = 0
    msmk: int = 0
    zms: int = 0
    gr: int = 0

    yn3_date: int = Field(8, alias="yn3Date")
    yn2_date: int = Field(10, alias="yn2Date")
    yn1_date: int = Field(12, alias="yn1Date")
    r3_date: int = Field(14, alias="r3Date")
    r2_date: int = Field(16, alias="r2Date")
    r1_date: int = Field(18, alias="r1Date")
    kms_date: int = Field(20, alias="kmsDate")
    ms_date: int = Field(22, alias="msDate")
    msmk_date: int = Field(24, alias="msmkDate")
    zms_date: int = Field(26, alias="zmsDate")
    gr_date: int = Field(28, alias="grDate")

    trainer_total: int = Field(0, alias="trainerTotal")
    judge_total: int = Field(0, alias="judgeTotal")
    nonresident_judge: int = Field(0, alias="nonresidentJudge")
    dc: int = 0
    bc: int = 0
    tc: int = 0
    sc: int = 0
    fc: int = 0
    vrc: int = 0
    mc: int = 0

    first_place: list[str] = Field(default_factory=list, alias="firstPlace")
    second_place: list[str] = Field(default_factory=list, alias="secondPlace")
    last_place: list[str] = Field(default_factory=list, alias="lastPlace")

    complete: bool = Field(False)
    sports: list[SportFront] = Field(default_factory=list)

    @field_validator("ekp", mode="before")
    @classmethod
    def _clean_ekp(cls, v: str) -> str:
        if v is None:
            return ""
        m = re.search(r"\d{16}", str(v))
        return m.group() if m else str(v)

    @field_validator("beginning", "ending", mode="before")
    @classmethod
    def _fix_date(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            return v
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})$", v)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        m = re.match(r"(\d{2})\.(\d{2})$", v)
        if m:
            return f"{datetime.now().year}-{m.group(2)}-{m.group(1)}"
        return v
