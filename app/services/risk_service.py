from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.schemas.risk import RiskCreate
from app.utils.mongo_serializer import serialize_mongo_document


class RiskService:

    def __init__(self, risk_repository, industry_repository):
        self.risk_repository = risk_repository
        self.industry_repository = industry_repository

    async def get_all_risks(
        self,
        industry_slug: str | None = None,
        severity: str | None = None,
        is_active: bool | None = True,
    ):
        risks = await self.risk_repository.get_all_risks(
            industry_slug=industry_slug,
            severity=severity,
            is_active=is_active,
        )

        return [
            serialize_mongo_document(risk)
            for risk in risks
        ]

    async def get_risk_by_id(self, risk_id: str):
        risk = await self.risk_repository.get_risk_by_id(risk_id)

        if risk is None:
            raise ValueError("Risk not found")

        return serialize_mongo_document(risk)

    async def get_risks_by_industry(self, industry_slug: str):
        if not await self.industry_repository.exists(industry_slug):
            raise ValueError("Industry not found")

        risks = await self.risk_repository.get_risks_by_industry(
            industry_slug=industry_slug,
            is_active=True,
        )

        return [
            serialize_mongo_document(risk)
            for risk in risks
        ]

    async def create_risk(self, payload: RiskCreate):
        """
        Create either a V1 or V2 risk.

        V1:
            Existing canonical structure.

        V2:
            Generic block-based structure using views.*.blocks.

        The payload shape is preserved as much as possible.
        """

        document = payload.model_dump(
            mode="python",
            exclude_unset=True,
        )

        # Server-owned fields must never be accepted from the client.
        document.pop("_id", None)
        document.pop("created_at", None)
        document.pop("updated_at", None)

        self._normalize_document(
            document,
            document["risk_id"],
        )

        existing = await self.risk_repository.get_risk_by_risk_id(
            document["risk_id"]
        )

        if existing is not None:
            raise ConflictError("Risk ID already exists")

        now = datetime.now(timezone.utc)

        document["created_at"] = now
        document["updated_at"] = now

        try:
            return await self.risk_repository.create_risk(
                document
            )

        except DuplicateKeyError as exc:
            raise ConflictError(
                "Risk ID already exists"
            ) from exc

    async def update_risk(
        self,
        risk_id: str,
        payload: RiskCreate,
    ):
        """
        Replace/update an existing V1 or V2 risk while
        preserving server-owned fields.
        """

        if payload.risk_id != risk_id:
            raise ValidationAppError(
                "Risk ID cannot be changed"
            )

        existing = await self.risk_repository.get_risk_by_risk_id(
            risk_id
        )

        if existing is None:
            raise NotFoundError("Risk not found")

        document = payload.model_dump(
            mode="python",
            exclude_unset=True,
        )

        document.pop("_id", None)
        document.pop("created_at", None)
        document.pop("updated_at", None)

        self._normalize_document(
            document,
            risk_id,
        )

        document["updated_at"] = datetime.now(
            timezone.utc
        )

        updated = await self.risk_repository.update_risk_by_risk_id(
            risk_id,
            document,
        )

        if updated is None:
            raise NotFoundError("Risk not found")

        return updated

    async def delete_risk(self, risk_id: str) -> None:
        deleted = await self.risk_repository.delete_risk_by_risk_id(
            risk_id
        )

        if not deleted:
            raise NotFoundError("Risk not found")

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @classmethod
    def _normalize_document(
        cls,
        document: dict,
        risk_id: str,
    ) -> None:
        """
        Normalize shared fields and dispatch schema-specific
        normalization.

        V1 and V2 intentionally use separate normalization
        paths so generic V2 blocks are not rewritten into
        legacy V1 structures.
        """

        cls._normalize_sender(
            document,
            risk_id,
        )

        schema_version = document.get(
            "schema_version",
            1,
        )

        try:
            schema_version = int(schema_version)
        except (TypeError, ValueError):
            schema_version = 1

        if schema_version >= 2:
            cls._normalize_v2_document(document)
            return

        cls._normalize_v1_document(document)

    @staticmethod
    def _normalize_sender(
        document: dict,
        risk_id: str,
    ) -> None:
        """
        Keep sender.risk_id synchronized with the canonical
        top-level risk_id.
        """

        sender = document.get("sender")

        if not isinstance(sender, dict):
            return

        sender["risk_id"] = risk_id

    # ========================================================
    # V1 NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_v1_document(
        document: dict,
    ) -> None:
        """
        Preserve the existing V1 mitigation cleanup behavior.

        Placeholder mitigation rows are removed and remaining
        steps are renumbered.
        """

        mitigation = document.get("mitigation")

        if not isinstance(mitigation, dict):
            return

        steps = mitigation.get("steps")

        if not isinstance(steps, list):
            return

        real_steps = []

        for step in steps:
            if not isinstance(step, dict):
                continue

            title = step.get("title")
            description = step.get("description")
            owner = step.get("owner")

            is_placeholder = (
                title == "New mitigation step"
                and description in (None, "")
                and owner == ""
            )

            if not is_placeholder:
                real_steps.append(step)

        for number, step in enumerate(
            real_steps,
            start=1,
        ):
            step["step"] = number

        mitigation["steps"] = real_steps

    # ========================================================
    # V2 NORMALIZATION
    # ========================================================

    @classmethod
    def _normalize_v2_document(
        cls,
        document: dict,
    ) -> None:
        """
        V2 is intentionally generic.

        Do NOT convert:
            views.notification
            views.details
            views.mitigation

        into legacy:
            metrics
            details
            mitigation

        Generic blocks should remain structurally intact.
        """

        views = document.get("views")

        if not isinstance(views, dict):
            return

        for view_name in (
            "notification",
            "details",
            "mitigation",
        ):
            view = views.get(view_name)

            if not isinstance(view, dict):
                continue

            blocks = view.get("blocks")

            if not isinstance(blocks, list):
                continue

            cls._normalize_v2_blocks(blocks)

    @classmethod
    def _normalize_v2_blocks(
        cls,
        blocks: list,
    ) -> None:
        """
        Perform only safe generic cleanup.

        Unknown block types and unknown block properties are
        preserved.
        """

        for block in blocks:
            if not isinstance(block, dict):
                continue

            block_type = str(
                block.get("type", "")
            ).strip()

            if block_type:
                block["type"] = block_type

            if block_type in (
                "action_list",
                "action-list",
                "actions",
            ):
                cls._normalize_action_list_block(
                    block
                )

    @staticmethod
    def _normalize_action_list_block(
        block: dict,
    ) -> None:
        """
        Normalize action ordering without destroying generic
        action metadata such as:

            owner
            status
            priority
            due_date
            description
            links
            etc.
        """

        items = block.get("items")

        if not isinstance(items, list):
            return

        real_items = []

        for item in items:
            if isinstance(item, str):
                text = item.strip()

                if text:
                    real_items.append(item)

                continue

            if not isinstance(item, dict):
                continue

            title = str(
                item.get("title")
                or item.get("description")
                or item.get("action")
                or item.get("text")
                or ""
            ).strip()

            # Remove completely empty builder rows.
            if not title:
                continue

            real_items.append(item)

        for order, item in enumerate(
            real_items,
            start=1,
        ):
            if isinstance(item, dict):
                item["order"] = order

        block["items"] = real_items