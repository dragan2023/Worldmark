from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import IPType, ItineraryStatus


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
    daily_hours: int = Field(default=8, ge=1)
    companions: str | None = Field(default=None, max_length=100)
    origin_city: str = Field(default="待确认", min_length=1, max_length=100)
    return_city: str | None = Field(default=None, max_length=100)
    traveler_count: int = Field(default=1, ge=1)
    budget_amount: int | None = Field(default=None, ge=1)
    transport_preference: str = Field(default="地铁/轻轨", pattern="^(地铁/轻轨|公交车|打车)$")
    auto_fill_nearby: bool = True
    interests: list[str] = Field(default_factory=list)
    lodging_mode: str = Field(default="recommend", pattern="^(recommend|booked|none)$")
    lodging_name: str | None = Field(default=None, max_length=255)
    lodging_address: str | None = Field(default=None, max_length=500)
    lodging_city: str | None = Field(default=None, max_length=100)
    lodgings: list[LodgingInput] = Field(default_factory=list)
    must_visit_landmark_ids: list[int] = Field(default_factory=list)
    excluded_landmark_ids: list[int] = Field(default_factory=list)
    free_text: str | None = Field(default=None, max_length=1000)
    meituan_plan_content: str | None = Field(default=None, max_length=50000)
    confirmed_plan: bool = False
    confirmed_transports: list[ConfirmedTransportInput] = Field(default_factory=list)
    confirmed_lodgings: list[ConfirmedLodgingInput] = Field(default_factory=list)
    confirmed_items: list[ConfirmedItemInput] = Field(default_factory=list)
    landmark_costs: list[LandmarkCostInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates_and_selections(self) -> "ItineraryCreateRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
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
            day_count = (self.end_date - self.start_date).days + 1
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


class ItineraryStopResponse(BaseModel):
    landmark_id: int
    stop_order: int
    time_slot: str
    planned_minutes: int
    selection_reason: str
    user_note: str | None
    landmark_name: str
    work_title: str
    normalized_address: str
    transit_text: str | None
    data_updated_at: datetime


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
