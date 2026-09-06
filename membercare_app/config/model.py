import os


PROJECT_ID = "membercare-ai"

# Agent Runtime itself runs in us-central1.
#
# Gemini 3.7 Flash is accessed through the US multi-region.
MODEL_LOCATION = "us"

MODEL_NAME = "gemini-3.7-flash"


def configure_model_environment() -> None:
    """
    Configure MemberCareAI's Gemini / Vertex AI environment.

    Agent Runtime:
        us-central1

    Gemini model endpoint:
        us

    We explicitly disable automatic mTLS endpoint selection.

    In managed environments, Google's client libraries can choose
    an mTLS endpoint when GOOGLE_API_USE_MTLS_ENDPOINT defaults
    to "auto" and certificate information is available.

    MemberCareAI does not require device-certificate mTLS for
    the Vertex AI model invocation path, so force the standard
    Google API endpoint.
    """

    # Use Vertex AI rather than Gemini Developer API.
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

    # Vertex AI project used for Gemini.
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID

    # Gemini 3.7 Flash US multi-region.
    os.environ["GOOGLE_CLOUD_LOCATION"] = MODEL_LOCATION

    # --------------------------------------------------------
    # IMPORTANT: DISABLE AUTOMATIC MTLS ENDPOINT SELECTION
    # --------------------------------------------------------

    os.environ["GOOGLE_API_USE_MTLS_ENDPOINT"] = "never"

    os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"