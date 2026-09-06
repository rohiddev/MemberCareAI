from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import cloudpickle
import pydantic
import vertexai
from vertexai import types


# ---------------------------------------------------------------------
# GCP configuration
# ---------------------------------------------------------------------

PROJECT_ID = "membercare-ai"
PROJECT_NUMBER = "422936875002"
LOCATION = "us-central1"

STAGING_BUCKET = os.getenv(
    "MEMBERCARE_STAGING_BUCKET",
    "gs://membercare-ai-agent-runtime",
)


# ---------------------------------------------------------------------
# MemberCareAI knowledge configuration
#
# Local development:
#
#     KNOWLEDGE_BACKEND=local
#     -> Chroma
#
# Managed Agent Runtime:
#
#     KNOWLEDGE_BACKEND=vertex
#     -> Vertex AI RAG Engine
# ---------------------------------------------------------------------

KNOWLEDGE_BACKEND = "vertex"

RAG_LOCATION = "us-central1"

RAG_CORPUS = (
    "projects/422936875002/"
    "locations/us-central1/"
    "ragCorpora/4231527674100580352"
)


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

DIST_DIR = PROJECT_ROOT / "dist"

DEPLOYMENT_WHEEL_NAME = (
    "membercareai-0.1.0-py3-none-any.whl"
)

DEPLOYMENT_WHEEL = (
    PROJECT_ROOT
    / DEPLOYMENT_WHEEL_NAME
)


# ---------------------------------------------------------------------
# Wheel preparation
# ---------------------------------------------------------------------

def find_built_wheel() -> Path:
    """
    Locate the newest MemberCareAI wheel created by:

        uv build
    """

    wheels = sorted(
        DIST_DIR.glob(
            "membercareai-*.whl"
        ),
        key=lambda path: (
            path.stat().st_mtime
        ),
    )

    if not wheels:
        raise RuntimeError(
            "No MemberCareAI wheel found in dist/. "
            "Run `uv build` first."
        )

    return wheels[-1]


def prepare_deployment_wheel() -> Path:
    """
    Copy the built MemberCareAI wheel to the project root.

    Agent Runtime will:

      1. upload this file using extra_packages
      2. install it using requirements

    This is required because the cloudpickled AdkApp contains
    references to the membercare_app Python package.
    """

    # Never reuse an older wheel. A stale wheel can retain obsolete
    # Requires-Python and dependency metadata even when pyproject.toml
    # has already been corrected.
    DIST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    dist_wheel = (
        DIST_DIR
        / DEPLOYMENT_WHEEL_NAME
    )

    dist_wheel.unlink(
        missing_ok=True
    )

    DEPLOYMENT_WHEEL.unlink(
        missing_ok=True
    )

    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            str(DIST_DIR),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    source_wheel = find_built_wheel()

    print(
        "Built wheel:",
        source_wheel,
    )

    shutil.copy2(
        source_wheel,
        DEPLOYMENT_WHEEL,
    )

    print(
        "Deployment wheel:",
        DEPLOYMENT_WHEEL,
    )

    return DEPLOYMENT_WHEEL


def validate_wheel(
    wheel_path: Path,
) -> None:
    if not wheel_path.exists():
        raise RuntimeError(
            f"Wheel not found: {wheel_path}"
        )

    if wheel_path.stat().st_size == 0:
        raise RuntimeError(
            f"Wheel is empty: {wheel_path}"
        )

    with zipfile.ZipFile(
        wheel_path
    ) as wheel_archive:
        metadata_names = [
            name
            for name in wheel_archive.namelist()
            if name.endswith(
                ".dist-info/METADATA"
            )
        ]

        if len(metadata_names) != 1:
            raise RuntimeError(
                "Expected exactly one wheel METADATA file; "
                f"found {len(metadata_names)}."
            )

        metadata = (
            wheel_archive
            .read(metadata_names[0])
            .decode("utf-8")
        )

    if "Requires-Python: >=3.12" not in metadata:
        raise RuntimeError(
            "Deployment wheel must declare "
            "Requires-Python: >=3.12."
        )

    if "Requires-Dist: chromadb" in metadata:
        raise RuntimeError(
            "Deployment wheel still includes ChromaDB. "
            "Keep ChromaDB out of production dependencies."
        )


# ---------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------

def main() -> None:
    os.chdir(PROJECT_ROOT)

    wheel_path = (
        prepare_deployment_wheel()
    )

    validate_wheel(
        wheel_path
    )

    print()
    print("=" * 70)
    print(
        "MemberCareAI Agent Runtime Deployment"
    )
    print("=" * 70)

    print(
        "PROJECT:",
        PROJECT_ID,
    )

    print(
        "LOCATION:",
        LOCATION,
    )

    print(
        "STAGING BUCKET:",
        STAGING_BUCKET,
    )

    print(
        "KNOWLEDGE BACKEND:",
        KNOWLEDGE_BACKEND,
    )

    print(
        "RAG LOCATION:",
        RAG_LOCATION,
    )

    print(
        "RAG CORPUS:",
        RAG_CORPUS,
    )

    print(
        "WHEEL:",
        wheel_path,
    )

    print(
        "LOCAL CLOUDPICKLE:",
        cloudpickle.__version__,
    )

    print(
        "LOCAL PYDANTIC:",
        pydantic.__version__,
    )

    # -----------------------------------------------------------------
    # Vertex client
    #
    # This currently emits a FutureWarning because Google is moving
    # toward agentplatform.Client.
    #
    # We keep this path because it is the deployment API already proven
    # in MemberCareAI.
    # -----------------------------------------------------------------

    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
    )

    # -----------------------------------------------------------------
    # Import deployable ADK wrapper.
    #
    # membercare_app/runtime/agent_app.py exports:
    #
    #     agent_app = AdkApp(
    #         agent=root_agent,
    #         app_name="membercareai",
    #         enable_tracing=True,
    #     )
    # -----------------------------------------------------------------

    from membercare_app.runtime.agent_app import (
        agent_app,
    )

    print()
    print(
        "Agent app type:",
        type(agent_app),
    )

    # -----------------------------------------------------------------
    # Dependencies
    #
    # IMPORTANT:
    #
    # extra_packages uploads the wheel.
    #
    # DEPLOYMENT_WHEEL_NAME in requirements causes pip to install
    # membercare_app into the managed runtime.
    # -----------------------------------------------------------------

    # The MemberCareAI wheel declares the application dependencies.
    # Only pin serialization dependencies here and install the wheel;
    # this avoids giving the remote resolver two overlapping lists.
    requirements = [
        "google-cloud-aiplatform[agent_engines,adk]>=1.112",

        (
            f"cloudpickle=="
            f"{cloudpickle.__version__}"
        ),

        (
            f"pydantic=="
            f"{pydantic.__version__}"
        ),

        DEPLOYMENT_WHEEL_NAME,
    ]

    extra_packages = [
        DEPLOYMENT_WHEEL_NAME,
    ]

    # -----------------------------------------------------------------
    # Managed Agent Runtime environment
    # -----------------------------------------------------------------

    env_vars = {
        # Gemini through Vertex AI
        "GOOGLE_GENAI_USE_VERTEXAI": (
            "TRUE"
        ),
        # -------------------------------------------------------------
        # RAG backend selection
        # -------------------------------------------------------------
        "KNOWLEDGE_BACKEND": (
            KNOWLEDGE_BACKEND
        ),

        "MEMBERCARE_RAG_LOCATION": (
            RAG_LOCATION
        ),

        "MEMBERCARE_RAG_CORPUS": (
            RAG_CORPUS
        ),

        # -------------------------------------------------------------
        # Prevent mTLS endpoint selection.
        # -------------------------------------------------------------
        "GOOGLE_API_USE_MTLS_ENDPOINT": (
            "never"
        ),

        "GOOGLE_API_USE_CLIENT_CERTIFICATE": (
            "false"
        ),

        # -------------------------------------------------------------
        # Telemetry
        # -------------------------------------------------------------
        "OTEL_SDK_DISABLED": (
            "false"
        ),
    }

    print()
    print("=" * 70)
    print(
        "REMOTE REQUIREMENTS"
    )
    print("=" * 70)

    for requirement in requirements:
        print(requirement)

    print()
    print("=" * 70)
    print(
        "REMOTE ENVIRONMENT"
    )
    print("=" * 70)

    for key, value in env_vars.items():
        print(
            f"{key}={value}"
        )

    print()
    print("=" * 70)
    print(
        "CREATING MANAGED AGENT RUNTIME"
    )
    print("=" * 70)

    remote_agent = (
        client.agent_engines.create(
            agent=agent_app,
            config={
                "display_name": (
                    "MemberCareAI"
                ),

                "description": (
                    "Governed multi-agent healthcare "
                    "member experience platform."
                ),
                # Required by the installed vertexai SDK when an
                # in-memory agent object and extra_packages are used.
                "staging_bucket": (
                    STAGING_BUCKET
                ),

                "requirements": (
                    requirements
                ),

                "extra_packages": (
                    extra_packages
                ),

                "env_vars": (
                    env_vars
                ),
            },
        )
    )

    # -----------------------------------------------------------------
    # Deployment succeeded
    # -----------------------------------------------------------------

    resource_name = (
        remote_agent
        .api_resource
        .name
    )

    reasoning_engine_id = (
        resource_name
        .rsplit(
            "/",
            1,
        )[-1]
    )

    print()
    print("=" * 70)
    print(
        "DEPLOYMENT COMPLETE"
    )
    print("=" * 70)

    print()
    print(
        "RESOURCE:"
    )

    print(
        resource_name
    )

    print()
    print(
        "REASONING ENGINE ID:"
    )

    print(
        reasoning_engine_id
    )

    # -----------------------------------------------------------------
    # Agent identity
    # -----------------------------------------------------------------

    agent_identity = (
        "principal://"
        "agents.global."
        f"proj-{PROJECT_NUMBER}."
        "system.id.goog/"
        "resources/aiplatform/"
        f"projects/{PROJECT_NUMBER}/"
        f"locations/{LOCATION}/"
        "reasoningEngines/"
        f"{reasoning_engine_id}"
    )

    print()
    print("=" * 70)
    print(
        "AGENT RUNTIME IDENTITY"
    )
    print("=" * 70)

    print(
        agent_identity
    )

    # -----------------------------------------------------------------
    # Firestore IAM
    # -----------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "1. GRANT FIRESTORE ACCESS"
    )
    print("=" * 70)

    print(
        f"""
gcloud projects add-iam-policy-binding {PROJECT_ID} \\
  --member='{agent_identity}' \\
  --role='roles/datastore.user'
""".strip()
    )

    # -----------------------------------------------------------------
    # Cloud Run update
    # -----------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "2. UPDATE CLOUD RUN"
    )
    print("=" * 70)

    print(
        f"""
gcloud run services update membercare-api \\
  --project={PROJECT_ID} \\
  --region={LOCATION} \\
  --update-env-vars='MEMBERCARE_AGENT_RUNTIME_RESOURCE={resource_name}'
""".strip()
    )

    # -----------------------------------------------------------------
    # Expected architecture
    # -----------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "EXPECTED CLOUD KNOWLEDGE PATH"
    )
    print("=" * 70)

    print(
        """
Cloud Run
    ↓
Outer Orchestrator
    ↓
Managed Agent Runtime
    ↓
membercare_supervisor
    ↓
benefits_agent
    ↓
Tool Gateway
    ↓
search_plan_knowledge
    ↓
retriever.py
    ↓
KNOWLEDGE_BACKEND=vertex
    ↓
Vertex AI RAG Engine
    ↓
membercare-policy-corpus
""".strip()
    )


if __name__ == "__main__":
    main()