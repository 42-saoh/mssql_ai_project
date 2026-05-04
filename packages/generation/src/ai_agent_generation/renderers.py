from __future__ import annotations

from typing import Protocol

from ai_agent_domain import ArtifactType

from ai_agent_generation.models import GenerationContext, RenderedArtifact


class ArtifactRenderer(Protocol):
    artifact_type: ArtifactType

    def render(self, context: GenerationContext) -> RenderedArtifact:
        """Render a draft artifact from canonical/generation context."""
