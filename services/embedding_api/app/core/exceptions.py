class DisageException(Exception):

    def __init__(

        self,

        message: str,

        status_code: int = 500

    ):

        self.message = message

        self.status_code = status_code

        super().__init__(message)


class RetrievalException(DisageException):

    pass


class EmbeddingException(DisageException):

    pass


class ChromaException(DisageException):

    pass


class LLMException(DisageException):

    pass


class ValidationException(DisageException):

    def __init__(

        self,

        message: str

    ):

        super().__init__(

            message,

            400

        )