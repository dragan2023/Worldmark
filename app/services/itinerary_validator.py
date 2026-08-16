from collections.abc import Iterable


class ItineraryValidationError(ValueError):
    """Raised when generated or edited itinerary data breaks product constraints."""


class ItineraryValidator:
    def validate_days(self, days: Iterable[object], allowed_landmark_ids: set[int], expected_days: int) -> None:
        entries = list(days)
        if len(entries) != expected_days:
            raise ItineraryValidationError("The itinerary must contain every requested travel day.")
        seen_day_numbers: set[int] = set()
        for day in entries:
            day_number = getattr(day, "day_number")
            stops = list(getattr(day, "stops"))
            if day_number in seen_day_numbers or not 1 <= day_number <= expected_days:
                raise ItineraryValidationError("Itinerary day numbering is invalid.")
            seen_day_numbers.add(day_number)
            for stop in stops:
                if getattr(stop, "landmark_id") not in allowed_landmark_ids:
                    raise ItineraryValidationError("Itinerary contains a landmark outside the published candidate set.")
                if getattr(stop, "planned_minutes") <= 0:
                    raise ItineraryValidationError("Each stop needs a positive planned duration.")
