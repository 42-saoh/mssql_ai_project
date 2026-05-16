from __future__ import annotations

from dataclasses import replace
from typing import Any

from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType

from api_app.auth import Actor, VerifiedIdentity, canonical_role_set
from api_app.contracts import validation_storage_result
from api_app.lifecycle import (
    artifact_status_after_validation,
    bounded_artifact_records,
    ensure_artifact_can_change,
    ensure_job_transition,
)
from api_app.repositories import (
    AgentRunRecord,
    ArtifactRecord,
    AuditEventRecord,
    JobRecord,
    KnowledgeAssetRecord,
    KnowledgeAssetVersionRecord,
    KnowledgeEdgeRecord,
    KnowledgeExportRecord,
    KnowledgeFactRecord,
    KnowledgeFactSearchRecord,
    KnowledgePersistenceError,
    MetadataAnalysisRunRecord,
    MetadataCollectionRecord,
    ValidationReportRecord,
    WorkRequestRecord,
    prefixed_id,
    standardized_audit_payload,
    utc_now,
)


class MemoryWorkflowRepository:
    """In-memory WorkflowRepository adapter for fixture-first tests and local demos."""

    def __init__(self) -> None:
        self.requests: dict[str, WorkRequestRecord] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.metadata_collections: dict[str, MetadataCollectionRecord] = {}
        self.agent_runs: dict[str, AgentRunRecord] = {}
        self.artifacts: dict[str, ArtifactRecord] = {}
        self.validation_reports: dict[str, ValidationReportRecord] = {}
        self.knowledge_assets: dict[str, KnowledgeAssetRecord] = {}
        self.knowledge_versions: dict[str, KnowledgeAssetVersionRecord] = {}
        self.knowledge_exports: dict[str, KnowledgeExportRecord] = {}
        self.knowledge_job_links: set[tuple[str, str, str]] = set()
        self.metadata_analysis_runs: dict[str, MetadataAnalysisRunRecord] = {}
        self.audit_events: list[AuditEventRecord] = []
        self.auth_actors: dict[str, Actor] = {}

    def add_auth_actor(
        self,
        *,
        subject: str,
        login: str,
        email: str | None = None,
        roles: tuple[str, ...] = ("USER",),
        display_name: str | None = None,
    ) -> Actor:
        actor = Actor(
            actor_id=subject,
            login=login,
            email=email,
            roles=canonical_role_set(roles),
            display_name=display_name,
        )
        for candidate in (subject, login, email):
            if candidate:
                self.auth_actors[candidate.strip().lower()] = actor
        return actor

    def resolve_actor_roles(self, identity: VerifiedIdentity) -> Actor | None:
        for candidate in identity.lookup_candidates:
            actor = self.auth_actors.get(candidate.strip().lower())
            if actor is not None:
                return actor
        return None

    def create_request(
        self,
        *,
        db_profile_id: str,
        target: dict[str, Any],
        outputs: tuple[str, ...],
        options: dict[str, Any],
        request_hash: str,
        correlation_id: str,
        idempotency_key: str | None,
    ) -> WorkRequestRecord:
        record = WorkRequestRecord(
            request_id=prefixed_id("req"),
            db_profile_id=db_profile_id,
            target=target,
            outputs=outputs,
            options=options,
            request_hash=request_hash,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        self.requests[record.request_id] = record
        self.record_audit_event(
            action="REQUEST_SUBMITTED",
            target_type="WORK_REQUEST",
            target_ref_id=record.request_id,
            payload={
                "dbProfileId": db_profile_id,
                "outputs": list(outputs),
                "tracking": {
                    "correlationId": correlation_id,
                    "idempotencyKey": idempotency_key,
                    "requestHash": request_hash,
                },
            },
            correlation_id=correlation_id,
        )
        return replace(record)

    def find_request_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> WorkRequestRecord | None:
        for request in self.requests.values():
            if request.idempotency_key == idempotency_key:
                return replace(request)
        return None

    def update_request_status(self, request_id: str, status: JobStatus) -> None:
        request = self.requests[request_id]
        request.status = status
        request.updated_at = utc_now()

    def create_job(self, request_id: str, *, correlation_id: str | None = None) -> JobRecord:
        request = self.requests.get(request_id)
        record = JobRecord(
            job_id=prefixed_id("job"),
            request_id=request_id,
            correlation_id=correlation_id,
            db_profile_id=request.db_profile_id if request else None,
            target=dict(request.target) if request else None,
            outputs=tuple(request.outputs) if request else (),
        )
        self.jobs[record.job_id] = record
        return replace(record)

    def find_job_by_request_id(self, request_id: str) -> JobRecord | None:
        for job in self.jobs.values():
            if job.request_id == request_id:
                return replace(job)
        return None

    def transition_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        current_step: WorkflowStepType | None,
    ) -> JobRecord:
        job = self.jobs[job_id]
        ensure_job_transition(job.status, status)
        job.status = status
        job.current_step = current_step
        job.updated_at = utc_now()
        job.transitions.append((status, current_step))
        self.update_request_status(job.request_id, status)
        self.record_audit_event(
            action="JOB_TRANSITIONED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={
                "status": status.value,
                "currentStep": current_step.value if current_step else None,
            },
            correlation_id=job.correlation_id,
        )
        return replace(job)

    def fail_job(self, job_id: str, *, code: str, message: str) -> JobRecord:
        job = self.jobs[job_id]
        ensure_job_transition(job.status, JobStatus.FAILED)
        job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message
        job.updated_at = utc_now()
        job.transitions.append((JobStatus.FAILED, job.current_step))
        self.update_request_status(job.request_id, JobStatus.FAILED)
        self.record_audit_event(
            action="JOB_FAILED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={"code": code, "message": message},
            correlation_id=job.correlation_id,
        )
        return replace(job)

    def save_metadata_collection(
        self,
        *,
        job_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> MetadataCollectionRecord:
        record = MetadataCollectionRecord(
            metadata_id=prefixed_id("meta"),
            job_id=job_id,
            status=status,
            payload=payload,
        )
        self.metadata_collections[record.metadata_id] = record
        job = self.jobs.get(job_id)
        self.record_audit_event(
            action="METADATA_COLLECTED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={"status": status, "snapshotId": payload.get("snapshotId")},
            correlation_id=job.correlation_id if job else None,
        )
        return record

    def latest_metadata_for_job(self, job_id: str) -> MetadataCollectionRecord | None:
        records = [
            record for record in self.metadata_collections.values() if record.job_id == job_id
        ]
        return records[-1] if records else None

    def save_agent_run(
        self,
        *,
        job_id: str,
        agent_type: str,
        status: str,
        target_ref: str,
        summary: str,
        structured_output: dict[str, Any],
        model_invocation: dict[str, Any],
    ) -> AgentRunRecord:
        record = AgentRunRecord(
            agent_run_id=prefixed_id("agent"),
            job_id=job_id,
            agent_type=agent_type,
            status=status,
            target_ref=target_ref,
            summary=summary,
            structured_output=structured_output,
            model_invocation=model_invocation,
        )
        self.agent_runs[record.agent_run_id] = record
        job = self.jobs.get(job_id)
        self.record_audit_event(
            action="AGENT_RUN_RECORDED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={
                "agentRunId": record.agent_run_id,
                "agentType": agent_type,
                "status": status,
                "targetRef": target_ref,
                "modelInvocation": _public_model_invocation(model_invocation),
            },
            correlation_id=job.correlation_id if job else None,
        )
        return record

    def list_agent_runs(
        self,
        job_id: str,
        *,
        limit: int | None = None,
    ) -> list[AgentRunRecord] | None:
        if job_id not in self.jobs:
            return None
        runs = sorted(
            [record for record in self.agent_runs.values() if record.job_id == job_id],
            key=lambda record: (record.created_at, record.agent_run_id),
            reverse=True,
        )
        if limit is not None:
            runs = runs[: max(min(int(limit), 100), 1)]
        return runs

    def add_artifact(
        self,
        *,
        job_id: str,
        artifact_type: ArtifactType,
        title: str,
        content: str,
        evidence_refs: list[dict[str, Any]],
        generator_version: str,
        registry_refs: tuple[str, ...],
        assumptions: tuple[str, ...],
        review_required: bool,
        extra: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            artifact_id=prefixed_id("art"),
            job_id=job_id,
            type=artifact_type,
            status=ArtifactStatus.DRAFT,
            title=title,
            content=content,
            evidence_refs=evidence_refs,
            generator_version=generator_version,
            registry_refs=registry_refs,
            assumptions=assumptions,
            review_required=review_required,
            extra=extra or {},
        )
        self.artifacts[record.artifact_id] = record
        job = self.jobs.get(job_id)
        self.record_audit_event(
            action="ARTIFACT_CREATED",
            target_type="ARTIFACT",
            target_ref_id=record.artifact_id,
            payload={
                "artifactId": record.artifact_id,
                "jobId": job_id,
                "artifactType": artifact_type.value,
                "status": record.status.value,
            },
            correlation_id=job.correlation_id if job else None,
        )
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.jobs.get(job_id)

    def list_jobs(self, *, limit: int | None = None) -> list[JobRecord]:
        jobs = sorted(
            self.jobs.values(),
            key=lambda job: (job.created_at, job.job_id),
            reverse=True,
        )
        if limit is not None:
            jobs = jobs[: max(min(int(limit), 100), 1)]
        return [replace(job) for job in jobs]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.artifacts.get(artifact_id)

    def list_job_artifacts(
        self,
        job_id: str,
        *,
        limit: int | None = None,
    ) -> list[ArtifactRecord] | None:
        if job_id not in self.jobs:
            return None
        return bounded_artifact_records(
            [artifact for artifact in self.artifacts.values() if artifact.job_id == job_id],
            limit=limit,
        )

    def save_validation_report(
        self,
        *,
        artifact_id: str,
        status: str,
        checks: list[dict[str, str]],
        missing_evidence: list[str],
        manual_review_points: list[str],
        correlation_id: str | None = None,
        actor: str = "api-system",
    ) -> ValidationReportRecord:
        artifact = self.artifacts[artifact_id]
        next_status = artifact_status_after_validation(status, artifact.status)
        ensure_artifact_can_change(artifact.status, next_status)
        record = ValidationReportRecord(
            validation_report_id=prefixed_id("val"),
            artifact_id=artifact_id,
            status=status,
            checks=checks,
            missing_evidence=missing_evidence,
            manual_review_points=manual_review_points,
            storage_result=validation_storage_result(status),
        )
        self.validation_reports[record.validation_report_id] = record
        artifact.latest_validation_report_id = record.validation_report_id
        artifact.latest_validation_status = record.status
        artifact.updated_at = utc_now()
        artifact.status = next_status
        self.record_audit_event(
            action="ARTIFACT_VALIDATED",
            target_type="ARTIFACT",
            target_ref_id=artifact_id,
            payload={
                "status": status,
                "storageResult": record.storage_result,
                "validationReportId": record.validation_report_id,
            },
            correlation_id=correlation_id or self.jobs[artifact.job_id].correlation_id,
            actor=actor,
        )
        return record

    def latest_validation_for(self, artifact_id: str) -> ValidationReportRecord | None:
        artifact = self.artifacts.get(artifact_id)
        if artifact is None or artifact.latest_validation_report_id is None:
            return None
        return self.validation_reports.get(artifact.latest_validation_report_id)

    def has_validation_report(self, validation_report_id: str) -> bool:
        return validation_report_id in self.validation_reports

    def record_audit_event(
        self,
        *,
        action: str,
        target_type: str,
        target_ref_id: str,
        payload: dict[str, Any],
        actor: str = "api-system",
        correlation_id: str | None = None,
    ) -> AuditEventRecord:
        audit_payload = standardized_audit_payload(
            action=action,
            target_type=target_type,
            target_ref_id=target_ref_id,
            payload=payload,
            actor=actor,
            correlation_id=correlation_id,
        )
        record = AuditEventRecord(
            audit_id=prefixed_id("audit"),
            action=action,
            target_type=target_type,
            target_ref_id=target_ref_id,
            payload=audit_payload,
            actor=actor,
            correlation_id=correlation_id,
        )
        self.audit_events.append(record)
        return record

    def upsert_knowledge_asset(
        self,
        *,
        job_id: str | None,
        db_profile_id: str,
        asset_kind: str,
        target: dict[str, str],
        payload: dict[str, Any],
        facts: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        content_hash: str,
    ) -> KnowledgeAssetVersionRecord:
        target_type = str(target.get("type") or "OBJECT")
        target_schema = str(target.get("schema") or "")
        target_name = str(target.get("name") or "")
        logical_key = "|".join(
            [db_profile_id, asset_kind, target_type, target_schema, target_name]
        ).lower()
        asset = next(
            (
                item
                for item in self.knowledge_assets.values()
                if item.logical_key == logical_key
            ),
            None,
        )
        if asset is None:
            asset = KnowledgeAssetRecord(
                asset_id=prefixed_id("know"),
                asset_kind=asset_kind,
                db_profile_id=db_profile_id,
                target_type=target_type,
                target_schema=target_schema,
                target_name=target_name,
                logical_key=logical_key,
                source_job_id=job_id,
            )
            self.knowledge_assets[asset.asset_id] = asset
        if asset.content_hash == content_hash and asset.current_version_id:
            version = self.knowledge_versions[asset.current_version_id]
            if job_id and not asset.source_job_id:
                asset.source_job_id = job_id
            self._link_knowledge_asset_to_job(job_id, asset.asset_id, version.version_id)
            return version

        version_no = asset.current_version_no + 1
        version_id = prefixed_id("knowv")
        fact_records = [
            KnowledgeFactRecord(
                fact_id=str(fact.get("factId") or fact.get("id") or prefixed_id("fact")),
                version_id=version_id,
                asset_id=asset.asset_id,
                fact_type=str(fact.get("factType") or fact.get("type") or asset_kind),
                object_ref=str(fact.get("objectRef") or ""),
                summary=str(fact.get("summary") or ""),
                status=str(fact.get("status") or "REVIEW_REQUIRED"),
                evidence_refs=[str(ref) for ref in fact.get("evidenceRefs", [])],
                payload=dict(fact.get("payload") or {}),
                content_hash=str(fact.get("contentHash") or content_hash),
            )
            for fact in facts
            if isinstance(fact, dict)
        ]
        edge_records = [
            KnowledgeEdgeRecord(
                edge_id=str(edge.get("edgeId") or prefixed_id("edge")),
                version_id=version_id,
                asset_id=asset.asset_id,
                from_fact_id=str(edge.get("fromFactId") or edge.get("from") or ""),
                to_fact_id=str(edge.get("toFactId") or edge.get("to") or ""),
                edge_type=str(edge.get("edgeType") or edge.get("type") or "DERIVED_FROM"),
                evidence_refs=[str(ref) for ref in edge.get("evidenceRefs", [])],
                payload=dict(edge.get("payload") or {}),
            )
            for edge in edges
            if isinstance(edge, dict)
        ]
        version = KnowledgeAssetVersionRecord(
            version_id=version_id,
            asset_id=asset.asset_id,
            version_no=version_no,
            content_hash=content_hash,
            payload=payload,
            facts=fact_records,
            edges=edge_records,
            source_job_id=job_id,
        )
        self.knowledge_versions[version_id] = version
        asset.current_version_id = version_id
        asset.current_version_no = version_no
        asset.content_hash = content_hash
        asset.updated_at = utc_now()
        if job_id and not asset.source_job_id:
            asset.source_job_id = job_id
        self._link_knowledge_asset_to_job(job_id, asset.asset_id, version_id)
        self.record_audit_event(
            action="KNOWLEDGE_ASSET_VERSIONED",
            target_type="KNOWLEDGE_ASSET",
            target_ref_id=asset.asset_id,
            payload={
                "assetKind": asset_kind,
                "versionId": version_id,
                "versionNo": version_no,
                "contentHash": content_hash,
                "sourceJobId": job_id,
            },
            correlation_id=self.jobs[job_id].correlation_id if job_id in self.jobs else None,
        )
        return version

    def list_job_knowledge_assets(self, job_id: str) -> list[KnowledgeAssetRecord] | None:
        if job_id not in self.jobs:
            return None
        latest_linked_versions: dict[str, KnowledgeAssetVersionRecord] = {}
        for linked_job_id, asset_id, version_id in self.knowledge_job_links:
            if linked_job_id != job_id:
                continue
            version = self.knowledge_versions.get(version_id)
            if version is None:
                continue
            existing = latest_linked_versions.get(asset_id)
            if existing is None or version.version_no > existing.version_no:
                latest_linked_versions[asset_id] = version
        assets: list[KnowledgeAssetRecord] = []
        for asset_id, version in latest_linked_versions.items():
            asset = self.knowledge_assets.get(asset_id)
            if asset is None:
                continue
            assets.append(self._asset_with_version_state(asset, version))
        return sorted(assets, key=lambda asset: (asset.updated_at, asset.asset_id), reverse=True)

    def list_knowledge_assets(
        self,
        *,
        asset_kind: str | None = None,
        db_profile_id: str | None = None,
        target_type: str | None = None,
        target_schema: str | None = None,
        target_name: str | None = None,
        lifecycle_status: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeAssetRecord]:
        assets: list[KnowledgeAssetRecord] = []
        for asset in self.knowledge_assets.values():
            version = (
                self.knowledge_versions.get(asset.current_version_id)
                if asset.current_version_id
                else None
            )
            candidate = self._asset_with_version_state(asset, version)
            if not self._asset_matches_filters(
                candidate,
                asset_kind=asset_kind,
                db_profile_id=db_profile_id,
                target_type=target_type,
                target_schema=target_schema,
                target_name=target_name,
                lifecycle_status=lifecycle_status,
            ):
                continue
            if lifecycle_status is None and candidate.lifecycle_status == "ARCHIVED":
                continue
            assets.append(candidate)
        return sorted(
            assets,
            key=lambda item: (item.updated_at, item.asset_id),
            reverse=True,
        )[: max(1, min(int(limit), 200))]

    def get_knowledge_asset(self, asset_id: str) -> KnowledgeAssetRecord | None:
        asset = self.knowledge_assets.get(asset_id)
        if asset is None:
            return None
        version = (
            self.knowledge_versions.get(asset.current_version_id)
            if asset.current_version_id
            else None
        )
        return self._asset_with_version_state(asset, version)

    def list_knowledge_asset_versions(
        self,
        asset_id: str,
    ) -> list[KnowledgeAssetVersionRecord] | None:
        if asset_id not in self.knowledge_assets:
            return None
        return sorted(
            [
                replace(version)
                for version in self.knowledge_versions.values()
                if version.asset_id == asset_id
            ],
            key=lambda version: version.version_no,
            reverse=True,
        )

    def get_knowledge_asset_version(
        self,
        asset_id: str,
        version_id: str,
    ) -> KnowledgeAssetVersionRecord | None:
        if asset_id not in self.knowledge_assets:
            return None
        version = self.knowledge_versions.get(version_id)
        if version is None or version.asset_id != asset_id:
            return None
        return replace(version)

    def list_knowledge_facts(
        self,
        asset_id: str,
        version_id: str,
    ) -> tuple[list[KnowledgeFactRecord], list[KnowledgeEdgeRecord]] | None:
        version = self.get_knowledge_asset_version(asset_id, version_id)
        if version is None:
            return None
        return (list(version.facts), list(version.edges))

    def search_knowledge_facts(
        self,
        *,
        object_ref: str | None = None,
        fact_type: str | None = None,
        status: str | None = None,
        asset_kind: str | None = None,
        target_name: str | None = None,
        lifecycle_status: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeFactSearchRecord]:
        results: list[KnowledgeFactSearchRecord] = []
        object_ref_filter = str(object_ref or "").lower()
        for version in self.knowledge_versions.values():
            asset = self.knowledge_assets.get(version.asset_id)
            if asset is None:
                continue
            if lifecycle_status is None and version.lifecycle_status == "ARCHIVED":
                continue
            if lifecycle_status and version.lifecycle_status != lifecycle_status:
                continue
            if asset_kind and asset.asset_kind != asset_kind:
                continue
            if target_name and asset.target_name != target_name:
                continue
            for fact in version.facts:
                if object_ref_filter and object_ref_filter not in fact.object_ref.lower():
                    continue
                if fact_type and fact.fact_type != fact_type:
                    continue
                if status and fact.status != status:
                    continue
                results.append(
                    KnowledgeFactSearchRecord(
                        asset_id=asset.asset_id,
                        asset_kind=asset.asset_kind,
                        version_id=version.version_id,
                        lifecycle_status=version.lifecycle_status,
                        fact=replace(fact),
                    )
                )
        return results[: max(1, min(int(limit), 200))]

    def save_knowledge_export(
        self,
        *,
        export_format: str,
        content_type: str,
        content: str,
        content_hash: str,
        asset_ids: list[str],
    ) -> KnowledgeExportRecord:
        record = KnowledgeExportRecord(
            export_id=prefixed_id("kexp"),
            format=export_format,
            content_type=content_type,
            content=content,
            content_hash=content_hash,
            asset_ids=asset_ids,
        )
        self.knowledge_exports[record.export_id] = record
        self.record_audit_event(
            action="KNOWLEDGE_EXPORTED",
            target_type="KNOWLEDGE_EXPORT",
            target_ref_id=record.export_id,
            payload={
                "format": export_format,
                "contentHash": content_hash,
                "assetIds": asset_ids,
            },
        )
        return record

    def create_metadata_analysis_run(
        self,
        *,
        run_id: str,
        request: dict[str, Any],
    ) -> MetadataAnalysisRunRecord:
        record = MetadataAnalysisRunRecord(
            run_id=run_id,
            status="QUEUED",
            request=dict(request),
        )
        self.metadata_analysis_runs[run_id] = record
        return replace(record)

    def get_metadata_analysis_run(self, run_id: str) -> MetadataAnalysisRunRecord | None:
        record = self.metadata_analysis_runs.get(run_id)
        return replace(record) if record else None

    def mark_metadata_analysis_run_running(self, run_id: str) -> MetadataAnalysisRunRecord:
        record = self.metadata_analysis_runs[run_id]
        record.status = "RUNNING"
        record.started_at = utc_now()
        return replace(record)

    def mark_metadata_analysis_run_succeeded(
        self,
        run_id: str,
        *,
        analysis: dict[str, Any],
    ) -> MetadataAnalysisRunRecord:
        record = self.metadata_analysis_runs[run_id]
        record.status = "SUCCEEDED"
        record.completed_at = utc_now()
        record.analysis = dict(analysis)
        record.error = None
        return replace(record)

    def mark_metadata_analysis_run_failed(
        self,
        run_id: str,
        *,
        error: dict[str, Any],
    ) -> MetadataAnalysisRunRecord:
        record = self.metadata_analysis_runs[run_id]
        record.status = "FAILED"
        record.completed_at = utc_now()
        record.error = dict(error)
        return replace(record)

    def _link_knowledge_asset_to_job(
        self,
        job_id: str | None,
        asset_id: str,
        version_id: str,
    ) -> None:
        if not job_id:
            return
        self.knowledge_job_links.add((job_id, asset_id, version_id))

    def _asset_with_version_state(
        self,
        asset: KnowledgeAssetRecord,
        version: KnowledgeAssetVersionRecord | None,
    ) -> KnowledgeAssetRecord:
        if version is None:
            return replace(asset)
        return replace(
            asset,
            current_version_id=version.version_id,
            current_version_no=version.version_no,
            content_hash=version.content_hash,
            lifecycle_status=version.lifecycle_status,
            archived_at=version.archived_at,
        )

    def _asset_matches_filters(
        self,
        asset: KnowledgeAssetRecord,
        *,
        asset_kind: str | None,
        db_profile_id: str | None,
        target_type: str | None,
        target_schema: str | None,
        target_name: str | None,
        lifecycle_status: str | None,
    ) -> bool:
        return (
            (asset_kind is None or asset.asset_kind == asset_kind)
            and (db_profile_id is None or asset.db_profile_id == db_profile_id)
            and (target_type is None or asset.target_type == target_type)
            and (target_schema is None or asset.target_schema == target_schema)
            and (target_name is None or asset.target_name == target_name)
            and (
                lifecycle_status is None
                or asset.lifecycle_status == lifecycle_status
            )
        )


def _public_model_invocation(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key
        in {
            "provider",
            "model",
            "modelProfileId",
            "modelRegistryRef",
            "reasoningEffort",
            "promptVersion",
            "outputSchemaVersion",
            "inputHash",
            "promptHash",
            "outputHash",
            "status",
            "tokenUsage",
            "latencyMs",
            "analysisCoverage",
            "sourceContextSummary",
            "componentInvocations",
        }
    }
