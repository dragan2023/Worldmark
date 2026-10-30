from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import IPType, ItineraryStatus

# 产品容量上限：与页面表单提示一致，防止用超长日期跨度或超大数组放大调用量。
MAX_TRIP_DAYS = 30
MAX_REQUIRED_LANDMARKS = 20
MAX_LODGINGS = 10
MAX_CONFIRMED_ITEMS = 60


class LodgingInput(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)


class ConfirmedTransportInput(BaseModel):
    leg_label: str = Field(min_length=1, max_length=50)
    departure: str = Field(min_length=1, max_length=100)
    arrival: str = Field(min_length=1, max_length=100)
    travel_date: date
    mode: str = Field(pattern="^(flight|train)$")
    option_id: str = Field(min_length=1, max_length=255)
    seat: str | None = Field(default=None, max_length=100)
    price: int = Field(ge=0)


class ConfirmedLodgingInput(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    nightly_price: int = Field(ge=0)


class ConfirmedItemInput(BaseModel):
    city: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    item_type: str = Field(pattern="^(scenic|food)$")
    price: int = Field(default=0, ge=0)
    address: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)


class LandmarkCostInput(BaseModel):
    landmark_id: int = Field(gt=0)
    price: int = Field(ge=0)


class ItineraryCreateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    ip_type: IPType | None = None
    work: str | None = Field(default=None, max_length=255)
    start_date: date
    end_date: date
    daily_hours: int = Field(default=8, ge=1, le=16)
    companions: str | None = Field(default=None, max_length=100)
    origin_city: str = Field(default="待确认", min_length=1, max_length=100)
    return_city: str | None = Field(default=None, max_length=100)
    traveler_count: int = Field(default=1, ge=1, le=30)
    budget_amount: int | None = Field(default=None, ge=1, le=10_000_000)
    transport_preference: str = Field(default="地铁/轻轨", pattern="^(地铁/轻轨|公交车|打车)$")
    auto_fill_nearby: bool = True
    interests: list[str] = Field(default_factory=list, max_length=12)
    lodging_mode: str = Field(default="recommend", pattern="^(recommend|booked|none)$")
    lodging_name: str | None = Field(default=None, max_length=255)
    lodging_address: str | None = Field(default=None, max_length=500)
    lodging_city: str | None = Field(default=None, max_length=100)
    lodgings: list[LodgingInput] = Field(default_factory=list, max_length=MAX_LODGINGS)
    must_visit_landmark_ids: list[int] = Field(default_factory=list, max_length=MAX_REQUIRED_LANDMARKS)
    excluded_landmark_ids: list[int] = Field(default_factory=list, max_length=MAX_REQUIRED_LANDMARKS)
    free_text: str | None = Field(default=None, max_length=1000)
    meituan_plan_content: str | None = Field(default=None, max_length=50000)
    confirmed_plan: bool = False
    confirmed_transports: list[ConfirmedTransportInput] = Field(default_factory=list, max_length=MAX_CONFIRMED_ITEMS)
    confirmed_lodgings: list[ConfirmedLodgingInput] = Field(default_factory=list, max_length=MAX_LODGINGS)
    confirmed_items: list[ConfirmedItemInput] = Field(default_factory=list, max_length=MAX_CONFIRMED_ITEMS)
    landmark_costs: list[LandmarkCostInput] = Field(default_factory=list, max_length=MAX_REQUIRED_LANDMARKS)

    @model_validator(mode="after")
    def validate_dates_and_selections(self) -> "ItineraryCreateRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        day_count = (self.end_date - self.start_date).days + 1
        if day_count > MAX_TRIP_DAYS:
            raise ValueError(f"单次行程最多 {MAX_TRIP_DAYS} 天，请拆分后再规划")
        if set(self.must_visit_landmark_ids) & set(self.excluded_landmark_ids):
            raise ValueError("a landmark cannot be both required and excluded")
        if not self.must_visit_landmark_ids and not self.work:
            raise ValueError("select at least one required landmark or an IP work")
        if self.lodging_mode == "booked":
            if not self.lodgings and not (self.lodging_name or self.lodging_address):
                raise ValueError("provide at least one booked lodging")
            if any(not (item.name or item.address) for item in self.lodgings):
                raise ValueError("each booked lodging needs a name or address")
        if self.confirmed_plan:
            attraction_capacity = max(day_count, (self.daily_hours // 3) * day_count)
            selected_scenic_count = sum(item.item_type == "scenic" for item in self.confirmed_items)
            selected_food_count = sum(item.item_type == "food" for item in self.confirmed_items)
            if selected_scenic_count > max(0, attraction_capacity - len(self.must_visit_landmark_ids)):
                raise ValueError("too many supplemental attractions were selected for this itinerary")
            if selected_food_count > day_count * 3:
                raise ValueError("too many meals were selected for this itinerary")
        return self


class ItineraryStopEdit(BaseModel):
    landmark_id: int = Field(gt=0)
    time_slot: str = Field(min_length=1, max_length=20)
    planned_minutes: int = Field(ge=15, le=960)
    selection_reason: str = Field(min_length=1, max_length=1000)
    user_note: str | None = Field(default=None, max_length=1000)


class ItineraryDayEdit(BaseModel):
    day_number: int = Field(ge=1)
    summary: str | None = Field(default=None, max_length=2000)
    stops: list[ItineraryStopEdit] = Field(default_factory=list)


class ItineraryUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    days: list[ItineraryDayEdit] = Field(default_factory=list)
    # 乐观并发：客户端提交它读到的版本号，服务端不一致时返回 409。
    expected_version: int | None = Field(default=None, ge=1)


class ItineraryStopResponse(BaseModel):
    landmark_id: int
    stop_order: int
    time_slot: str
    planned_minutes: int
    selection_reason: str
    user_note: str | None
    landmark_name: str
    work_title: str
    normalized_address: str | None = None
    transit_text: str | None = None
    data_updated_at: datetime | None = None
    # available：正常；unavailable：地点已下架/软删，仅保留占位与用户备注
    availability: str = "available"
    availability_note: str | None = None


class ItineraryDayResponse(BaseModel):
    day_number: int
    itinerary_date: date
    summary: str | None
    stops: list[ItineraryStopResponse]
    supplemental_items: list[dict]
    travel_context: dict


class ItineraryResponse(BaseModel):
    id: int
    title: str
    status: ItineraryStatus
    version: int
    start_date: date
    end_date: date
    daily_hours: int
    origin_city: str | None
    return_city: str | None
    traveler_count: int
    budget_amount: int | None
    transport_preference: str | None
    auto_fill_nearby: bool
    interests: list[str]
    lodging_mode: str
    lodging_name: str | None
    lodging_address: str | None
    lodging_city: str | None
    lodging_reference: dict | None
    transport_reference: dict | None
    budget_summary: dict | None
    destination_country: str | None
    destination_province: str | None
    destination_city: str | None
    generator_version: str
    # basic（本地确定性生成）/ llm（模型生成）/ enhanced（外部服务增强）
    generation_mode: str = "basic"
    enhancement_warnings: list[str] = Field(default_factory=list)
    validation_error_summary: str | None
    created_at: datetime
    days: list[ItineraryDayResponse]
    disclaimer: str


class ItineraryListItem(BaseModel):
    id: int
    title: str
    status: ItineraryStatus
    version: int
    start_date: date
    end_date: date
    created_at: datetime


class ItineraryListResponse(BaseModel):
    items: list[ItineraryListItem]
