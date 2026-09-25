from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class RiskDestinationOverrideUpsert(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    overrides: dict[str, Any] = Field(
        default_factory=dict
    )

    is_active: bool = True

    @field_validator("overrides")
    @classmethod
    def validate_overrides(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:

        # Prevent accidental double nesting:
        #
        # {
        #   "overrides": {
        #       "overrides": {...}
        #   }
        # }
        #
        # Correct:
        #
        # {
        #   "overrides": {
        #       "summary": "...",
        #       "subtitle": "...",
        #       "views": {...}
        #   }
        # }

        if "overrides" in value:
            raise ValueError(
                "Nested 'overrides' is not allowed. "
                "Place risk fields directly inside 'overrides'."
            )

        # Fields that must never be changed
        # by a destination-specific override.
        protected_fields = {
            "_id",
            "id",
            "risk_id",
            "created_at",
            "updated_at",
        }

        invalid_fields = (
            protected_fields.intersection(
                value.keys()
            )
        )

        if invalid_fields:
            fields = ", ".join(
                sorted(invalid_fields)
            )

            raise ValueError(
                "Destination override cannot modify "
                f"protected fields: {fields}"
            )

        return value
