from app.models.learning.follow_up import FollowUp

from app.services.retrieval.multi_query_retrieval_service import (
    MultiQueryRetrievalService,
)


class FollowUpValidationService:

    MAX_FOLLOW_UPS = 3

    def __init__(
        self,
        retrieval_service: MultiQueryRetrievalService,
    ):
        self.retrieval_service = retrieval_service

    def validate(
        self,
        follow_ups: list[FollowUp],
    ) -> list[FollowUp]:

        validated: list[FollowUp] = []
        seen: set[str] = set()

        for follow_up in follow_ups:

            question = follow_up.question.strip()

            if not question:
                continue

            if question in seen:
                continue

            result = self.retrieval_service.search(
                question=question,
                limit=1,
            )

            if not result.items:
                continue

            seen.add(question)

            validated.append(follow_up)

            if len(validated) >= self.MAX_FOLLOW_UPS:
                break

        return validated