from app.models.learning.follow_up import FollowUp


class LearningFollowUpService:

    MAX_FOLLOW_UPS = 3

    def generate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> list[FollowUp]:
        if not contexts:
            return []

        follow_ups: list[FollowUp] = []

        for context in contexts:
            if "@" in context and "Override" in context:
                follow_ups.append(
                    FollowUp(
                        question="@Overrideアノテーションとは？",
                        reason="回答に関連するアノテーションの理解を深めるため",
                    )
                )

            if "Objectクラス" in context:
                follow_ups.append(
                    FollowUp(
                        question="Objectクラスとは？",
                        reason="回答に登場するObjectクラスの理解を深めるため",
                    )
                )

            if "toString" in context:
                follow_ups.append(
                    FollowUp(
                        question="ObjectクラスのtoString()とは？",
                        reason="回答に登場するtoString()の理解を深めるため",
                    )
                )

            if len(follow_ups) >= self.MAX_FOLLOW_UPS:
                break

        return self._deduplicate(follow_ups)

    def _deduplicate(
        self,
        follow_ups: list[FollowUp],
    ) -> list[FollowUp]:
        result: list[FollowUp] = []
        seen: set[str] = set()

        for follow_up in follow_ups:
            if follow_up.question in seen:
                continue

            seen.add(follow_up.question)
            result.append(follow_up)

        return result[: self.MAX_FOLLOW_UPS]