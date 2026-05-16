from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_agent_domain import ArtifactStatus, ArtifactType, RequestedOutputType

from ai_agent_generation.models import (
    ColumnSpec,
    DraftFile,
    GENERATOR_VERSION,
    GenerationContext,
    RenderedArtifact,
    RenderedBundle,
)
from ai_agent_generation.policy import (
    GenerationPolicyAssets,
    GenerationPolicyError,
    load_generation_assets,
    validate_generation_assets,
)
from ai_agent_generation.utils import (
    ensure_trailing_newline,
    java_imports_for_types,
    korean_entity_label,
    snake_to_lower_camel,
    upper_first,
)

SP_WRAPPER_TEMPLATE_ID = "java_mybatis_sp_wrapper"
DTO_MODEL_TEMPLATE_ID = "java_mybatis_dto_model_bundle"


@dataclass(frozen=True)
class JavaMyBatisNames:
    context: GenerationContext
    assets: GenerationPolicyAssets

    @property
    def policy(self) -> Mapping[str, Any]:
        return self.assets.policy

    @property
    def dto_class_name(self) -> str:
        return self.class_name("dto")

    @property
    def vo_class_name(self) -> str:
        return self.class_name("vo")

    @property
    def model_class_name(self) -> str:
        return self.class_name("model")

    @property
    def service_class_name(self) -> str:
        return self.class_name("service")

    @property
    def mapper_class_name(self) -> str:
        return self.class_name("mapper")

    @property
    def model_package(self) -> str:
        return self.package("model")

    @property
    def service_package(self) -> str:
        return self.package("service")

    @property
    def mapper_package(self) -> str:
        return self.package("mapper")

    @property
    def mapper_method_name(self) -> str:
        pattern = str(self.policy["methodPatterns"]["mapperSelect"])
        return self._format(pattern)

    @property
    def service_method_name(self) -> str:
        pattern = str(self.policy["methodPatterns"]["listRetrieve"])
        return self._format(pattern)

    @property
    def mapper_namespace(self) -> str:
        rule = self.policy["mybatis"]["namespaceRule"]
        if rule != "full_mapper_interface_name":
            raise GenerationPolicyError(f"Unsupported MyBatis namespace rule: {rule}")
        return f"{self.mapper_package}.{self.mapper_class_name}"

    @property
    def mapper_sql_id(self) -> str:
        rule = self.policy["mybatis"]["sqlIdRule"]
        if rule != "same_as_mapper_method_name":
            raise GenerationPolicyError(f"Unsupported MyBatis SQL id rule: {rule}")
        return self.mapper_method_name

    @property
    def mapper_xml_path(self) -> str:
        pattern = str(self.policy["mybatis"]["mapperXmlPath"])
        return self._format(pattern)

    @property
    def mapper_xml_directory(self) -> str:
        return self.mapper_xml_path.rsplit("/", 1)[0]

    @property
    def mybatis_config_classpath(self) -> str:
        pattern = str(self.policy["mybatis"]["configPath"])
        path = self._format(pattern)
        return path.removeprefix("src/main/resources/")

    @property
    def message_key_example(self) -> str:
        pattern = str(self.policy["messages"]["patterns"]["business"])
        value = f"{self.context.message_prefix}.retrieve"
        return self._format(pattern, messageType="info", value=value, seq="001")

    @property
    def application_yml_root(self) -> str:
        pattern = str(self.policy["applicationYml"]["rootNode"])
        return self._format(pattern)

    def class_name(self, role: str) -> str:
        pattern = str(self.policy["classNames"][role])
        return self._format(pattern)

    def package(self, layer: str) -> str:
        pattern = str(self.policy["naming"]["packagePattern"])
        return self._format(pattern, layer=layer)

    def source_path(self, layer: str, class_name: str) -> str:
        return f"src/main/java/{self.package(layer).replace('.', '/')}/{class_name}.java"

    def sql_comment(self) -> str:
        pattern = str(self.policy["mybatis"]["sqlCommentPattern"])
        return self._format(
            pattern,
            Mapper=self.mapper_class_name,
            method=self.mapper_method_name,
        )

    def java_type_for_db_type(self, db_type: str) -> str:
        normalized = db_type.strip().lower().split("(", 1)[0]
        type_mapping = self.policy["fieldMapping"]["typeMappingDefaults"]
        return str(type_mapping.get(normalized, "String"))

    def field_name(self, physical_name: str) -> str:
        rule = self.policy["fieldMapping"]["nameTransform"]["rule"]
        if rule != "underscore_to_lowerCamel":
            raise GenerationPolicyError(f"Unsupported field name transform rule: {rule}")
        cleaned = physical_name.lstrip("@")
        if "_" in cleaned or cleaned.isupper():
            return snake_to_lower_camel(cleaned)
        return cleaned[:1].lower() + cleaned[1:]

    def db_parameter_name(self, physical_name: str) -> str:
        cleaned = physical_name.lstrip("@")
        return f"@{cleaned}" if cleaned else physical_name

    def _format(self, pattern: str, **extra_tokens: str) -> str:
        tokens = {
            "systemCode": self.context.system_code,
            "systemCodeLower": self.context.system_code_lower,
            "businessCodeLv1": self.context.business_code_lv1,
            "businessCodeLv2": self.context.business_code_lv2,
            "EntityName": self.context.entity_name,
            "entityName": self.context.entity_name_lower,
            "authorId": self.context.author_id,
        }
        tokens.update(extra_tokens)
        return pattern.format(**tokens)


class JavaMyBatisDraftRendererBase:
    template_id = ""
    requested_output_type = ""

    def __init__(self, assets: GenerationPolicyAssets | None = None) -> None:
        if assets is None:
            self.assets = load_generation_assets(template_ids=(self.template_id,))
        else:
            validate_generation_assets(assets, template_ids=(self.template_id,))
            self.assets = assets
        self._validate_template_requested_output()

    def names(self, context: GenerationContext) -> JavaMyBatisNames:
        return JavaMyBatisNames(context=context, assets=self.assets)

    def _validate_template_requested_output(self) -> None:
        registry_requested_output = str(
            self.assets.template(self.template_id)["requestedOutputType"]
        )
        if registry_requested_output != self.requested_output_type:
            raise GenerationPolicyError(
                "Java/MyBatis template registry requestedOutputType drift: "
                f"template `{self.template_id}` declares `{registry_requested_output}`, "
                f"renderer expects `{self.requested_output_type}`"
            )

    def render_manifest(
        self,
        context: GenerationContext,
        files: tuple[DraftFile, ...],
        names: JavaMyBatisNames,
        *,
        code_draft_summary: str,
    ) -> str:
        label = korean_entity_label(context.description, context.entity_name)
        evidence_lines = self._evidence_summary_lines(context)
        evidence_ref_lines = self._evidence_ref_lines(context)
        generated_file_lines = [
            f"- `{file.path}` ({file.artifact_type.value})" for file in files
        ]
        output_role_lines = self._output_role_lines()
        package_lines = self._package_structure_lines(files)
        snapshot_lines = json.dumps(
            context.sanitized_input_snapshot(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).splitlines()
        risk_lines = self._sql_risk_marker_lines()
        todo_lines = self._todo_lines(context)
        llm_conversion_lines = self._llm_conversion_lines(context)
        quality_summary_lines = self._quality_summary_lines(context)
        evidence_map_lines = self._evidence_map_lines(context, files)
        known_caveat_lines = self._known_caveat_lines(context)
        next_evidence_lines = self._next_evidence_lines(context)
        draft_readiness_lines = self._draft_readiness_lines(context)
        unconfirmed_lines = [
            f"- REVIEW_REQUIRED: `{marker}` 항목은 추가 근거 확보 전까지 caveat로 유지합니다."
            for marker in self.assets.todo_markers()
        ]

        lines = [
            f"# {context.sample_id}",
            "",
            "## input_interpretation",
            f"- systemCode: {context.system_code}",
            (
                "- businessCodeLv1/businessCodeLv2: "
                f"{context.business_code_lv1}/{context.business_code_lv2}"
            ),
            f"- entityName: {context.entity_name}",
            f"- generationMode: {context.generation_mode}",
            f"- resourceName: {context.resource_name}",
            f"- spName: {context.sp_name}",
            f"- tableName: {context.table_name}",
            "",
            "## registry_versions",
            f"- policy: `{self.assets.policy_ref}`",
            f"- template: `{self.assets.template_ref(self.template_id)}`",
            f"- registry: `{self.assets.registry_version}`",
            "",
            "## generator_metadata",
            f"- generatorVersion: `{GENERATOR_VERSION}`",
            f"- requestedOutputType: `{self.requested_output_type}`",
            f"- artifactStatus: `{ArtifactStatus.DRAFT.value}`",
            "- evidenceCaveat: `true`",
            "- draftQualityGate: `validation_only`",
            "",
            "## input_snapshot",
            f"- sanitizedSnapshotHash: `{context.input_snapshot_hash}`",
            "- sanitizedSnapshot:",
            "",
            "```json",
            *snapshot_lines,
            "```",
            "",
            "## generation_mode",
            f"- `{context.generation_mode}`",
            "- 이유: 생성 모드는 policy asset의 generationModes 기준을 따릅니다.",
            "",
            "## evidence_summary",
            *evidence_lines,
            "",
            "## evidence_refs",
            *evidence_ref_lines,
            "",
            "## package_structure",
            *package_lines,
            "",
            "## output_roles",
            *output_role_lines,
            "",
            "## generated_files",
            *generated_file_lines,
            "",
            "## code_draft",
            f"- {code_draft_summary}",
            "- generated_source_application: `not_performed`",
            "- target_application_write: `not_performed`",
            "",
            "## draft_change_summary",
            "- 모든 파일은 artifact preview/diff 대상으로만 생성되었습니다.",
            "- 실제 프로젝트 소스 반영, DDL/DML 실행, procedure 실행은 수행하지 않습니다.",
            "- 초안은 evidence map과 caveat를 함께 제공해 최초 설계 업무의 출발점을 줄입니다.",
            "",
            "## sql_risk_markers",
            *risk_lines,
            "",
            "## llm_conversion_guidance",
            *llm_conversion_lines,
            "",
            "## unconfirmed_areas",
            *unconfirmed_lines,
            "",
            "## message_and_config_examples",
            f"- message key 예시: `{names.message_key_example}`",
            f"- message value 예시: `{label} 목록을 조회했습니다.`",
            "- application yml 예시:",
            "",
            "```yaml",
            f"{names.application_yml_root}:",
            "  mybatis:",
            f"    config: classpath:/{names.mybatis_config_classpath}",
            "```",
            "",
            "## assumptions_and_todo",
            *todo_lines,
            "",
            "## quality_summary",
            *quality_summary_lines,
            "",
            "## evidence_map",
            *evidence_map_lines,
            "",
            "## known_caveats",
            *known_caveat_lines,
            "",
            "## next_evidence_to_collect",
            *next_evidence_lines,
            "",
            "## draft_readiness",
            *draft_readiness_lines,
        ]
        return ensure_trailing_newline("\n".join(lines))

    def render_data_class(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
        *,
        class_name: str,
        object_type_label: str,
    ) -> str:
        java_types = {names.java_type_for_db_type(column.db_type) for column in context.columns}
        imports = java_imports_for_types(java_types)
        label = korean_entity_label(context.description, context.entity_name)
        evidence = ", ".join(
            source.name for source in context.evidence_sources if source.name
        ) or "REVIEW_REQUIRED"
        lines = [f"package {names.model_package};", ""]
        for import_name in imports:
            lines.append(f"import {import_name};")
        if imports:
            lines.append("")
        lines.extend(
            [
                "/**",
                f" * {label} {object_type_label} 초안.",
                f" * evidence: {evidence}",
                " * REVIEW_REQUIRED: 필드/타입은 metadata evidence 기준 초안이다.",
                " */",
                f"public class {class_name} {{",
                "",
            ]
        )

        for index, column in enumerate(context.columns):
            if index:
                lines.append("")
            self._append_field(lines, column, names)

        for column in context.columns:
            self._append_accessor(lines, column, names)

        lines.append("}")
        return ensure_trailing_newline("\n".join(lines))

    def render_service(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames | None = None,
    ) -> str:
        names = names or self.names(context)
        label = korean_entity_label(context.description, context.entity_name)
        lines = [
            f"package {names.service_package};",
            "",
            "import java.util.List;",
            "",
            f"import {names.model_package}.{names.dto_class_name};",
            "",
            "/**",
            f" * {label} 서비스 초안.",
            " * REVIEW_REQUIRED: transaction boundary 는 evidence 확정 후 보강한다.",
            " */",
            f"public interface {names.service_class_name} {{",
            "",
            "    /**",
            f"     * {label} 목록을 조회한다.",
            "     *",
            "     * @param condition 조회 조건 DTO",
            f"     * @return {label} 목록",
            "     */",
            (
                f"    List<{names.dto_class_name}> {names.service_method_name}"
                f"({names.dto_class_name} condition);"
            ),
            "}",
        ]
        return ensure_trailing_newline("\n".join(lines))

    def render_mapper(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames | None = None,
    ) -> str:
        names = names or self.names(context)
        label = korean_entity_label(context.description, context.entity_name)
        lines = [
            f"package {names.mapper_package};",
            "",
            "import java.util.List;",
            "",
            f"import {names.model_package}.{names.dto_class_name};",
            "",
            "/**",
            f" * {label} Mapper 초안.",
            " * REVIEW_REQUIRED: Mapper XML namespace/sql id 와 함께 검토한다.",
            " */",
            f"public interface {names.mapper_class_name} {{",
            "",
            "    /**",
            f"     * {label} 목록을 조회한다.",
            "     *",
            "     * @param condition 조회 조건 DTO",
            f"     * @return {label} 목록",
            "     */",
            (
                f"    List<{names.dto_class_name}> {names.mapper_method_name}"
                f"({names.dto_class_name} condition);"
            ),
            "}",
        ]
        return ensure_trailing_newline("\n".join(lines))

    def render_mapper_xml(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames | None = None,
    ) -> str:
        names = names or self.names(context)
        param_lines = []
        for index, param in enumerate(context.input_params):
            comma = "," if index < len(context.input_params) - 1 else ""
            field_name = names.field_name(param.name)
            param_name = names.db_parameter_name(param.name)
            param_lines.append(f"      {param_name} = #{{{field_name}}}{comma}")
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<!DOCTYPE mapper",
            '  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"',
            '  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">',
            f'<mapper namespace="{names.mapper_namespace}">',
            "",
            f"  <!-- {names.sql_comment()} -->",
            f'  <select id="{names.mapper_sql_id}"',
            f'          parameterType="{names.model_package}.{names.dto_class_name}"',
            f'          resultType="{names.model_package}.{names.dto_class_name}">',
            f"    EXEC {context.sp_name}",
            *param_lines,
            "  </select>",
            "",
            "</mapper>",
        ]
        return ensure_trailing_newline("\n".join(lines))

    def _append_field(
        self,
        lines: list[str],
        column: ColumnSpec,
        names: JavaMyBatisNames,
    ) -> None:
        lines.append(f"    /** {column.description or column.name} */")
        java_type = names.java_type_for_db_type(column.db_type)
        field_name = names.field_name(column.name)
        lines.append(f"    private {java_type} {field_name};")

    def _append_accessor(
        self,
        lines: list[str],
        column: ColumnSpec,
        names: JavaMyBatisNames,
    ) -> None:
        field_name = names.field_name(column.name)
        method_suffix = upper_first(field_name)
        java_type = names.java_type_for_db_type(column.db_type)
        lines.extend(
            [
                "",
                f"    public {java_type} get{method_suffix}() {{",
                f"        return {field_name};",
                "    }",
                "",
                f"    public void set{method_suffix}({java_type} {field_name}) {{",
                f"        this.{field_name} = {field_name};",
                "    }",
            ]
        )

    def _evidence_summary_lines(self, context: GenerationContext) -> list[str]:
        lines = [
            f"- {source.display_type}: `{source.name}` - {source.reason}"
            for source in context.evidence_sources
        ]
        if not lines:
            lines.append("- REVIEW_REQUIRED: evidence source 가 비어 있음")
        lines.append("- DTO 필드 정의는 metadata column/result shape evidence 에 근거함")
        lines.append("- 모든 생성물은 draft-only artifact 이며 자동 적용 대상이 아님")
        return lines

    def _evidence_ref_lines(self, context: GenerationContext) -> list[str]:
        lines = []
        for ref in context.evidence_refs:
            line = f"- {ref.type}: `{ref.object_ref}` locator=`{ref.locator}`"
            if ref.snapshot_id:
                line = f"{line} snapshotId=`{ref.snapshot_id}`"
            lines.append(line)
        return lines or ["- REVIEW_REQUIRED: evidenceRefs 없음"]

    def _output_role_lines(self) -> list[str]:
        roles = self.assets.template(self.template_id)["outputRoles"]
        return [
            f"- {role}: {metadata['artifactType']}"
            for role, metadata in roles.items()
            if isinstance(metadata, Mapping)
        ]

    def _package_structure_lines(self, files: tuple[DraftFile, ...]) -> list[str]:
        lines: list[str] = []
        seen = set()
        for file in files:
            value = self._package_or_directory(file)
            if value not in seen:
                seen.add(value)
                lines.append(f"- `{value}`")
        return lines

    def _package_or_directory(self, file: DraftFile) -> str:
        if file.path.endswith(".java"):
            first_line = file.content.splitlines()[0]
            return first_line.removeprefix("package ").removesuffix(";")
        return file.path.rsplit("/", 1)[0]

    def _sql_risk_marker_lines(self) -> list[str]:
        return [
            f"- 상태 {marker['status']}: `{marker['code']}` - {marker['description']}"
            for marker in self.assets.sql_risk_markers(self.template_id)
        ]

    def _quality_summary_lines(self, context: GenerationContext) -> list[str]:
        source_count = len(context.evidence_sources)
        return [
            f"- evidenceSources: `{source_count}`",
            "- raw SQL text, row data, secrets, DDL/DML execution output은 포함하지 않습니다.",
            "- Java/MyBatis 코드는 설계 초안이며 validation 결과와 caveat를 함께 읽어야 합니다.",
        ]

    def _evidence_map_lines(
        self,
        context: GenerationContext,
        files: tuple[DraftFile, ...],
    ) -> list[str]:
        evidence_refs = ", ".join(ref.locator for ref in context.evidence_refs[:5])
        if not evidence_refs:
            evidence_refs = "REVIEW_REQUIRED:evidenceRefs 없음"
        return [
            f"- generatedFiles: `{len(files)}`",
            f"- primaryEvidence: {evidence_refs}",
            "- DTO/model fields: metadata columns and result shape evidence",
            "- Mapper/service shape: stored procedure signature and dependency/call-flow evidence",
        ]

    def _known_caveat_lines(self, context: GenerationContext) -> list[str]:
        lines = [
            "- REVIEW_REQUIRED는 근거 보강 필요 상태를 의미합니다.",
        ]
        lines.extend(
            f"- TODO(input): {assumption}"
            for assumption in context.evidence_assumptions
        )
        lines.extend(
            f"- TODO(policy.mustMarkUnknown): {marker}"
            for marker in self.assets.todo_markers()
        )
        return lines

    def _next_evidence_lines(self, context: GenerationContext) -> list[str]:
        return [
            f"- `{context.sp_name}`의 confirmed dependency procedure별 input/output, DML, transaction boundary를 보강합니다.",
            "- MyBatis resultMap이 필요한 nested/nullable/collection result shape evidence를 보강합니다.",
            "- 호출부에서 기대하는 service method contract, message key, paging/sorting semantics를 보강합니다.",
        ]

    def _draft_readiness_lines(self, context: GenerationContext) -> list[str]:
        return [
            "- Java/MyBatis package, class, mapper id, message key는 registry naming rule을 따릅니다.",
            "- DML/call-flow caveat가 남은 경우 구현 깊이는 mapper/service skeleton 수준으로 제한합니다.",
            f"- `{context.entity_name}` 초안은 최초 설계 리드타임 단축용이며 자동 적용 경로가 없습니다.",
        ]

    def _todo_lines(self, context: GenerationContext) -> list[str]:
        lines = [
            "- REVIEW_REQUIRED: 모든 파일은 draft-only 이며 추가 근거 확보 전 자동 반영하지 않습니다."
        ]
        lines.extend(f"- TODO(input): {assumption}" for assumption in context.evidence_assumptions)
        lines.extend(
            f"- TODO(policy.mustMarkUnknown): {marker}"
            for marker in self.assets.todo_markers()
        )
        return lines

    def _llm_conversion_lines(self, context: GenerationContext) -> list[str]:
        payload = context.value("llmAnalysis", {}) or {}
        if not isinstance(payload, dict):
            return ["- status: NOT_REQUESTED"]
        guidance = payload.get("conversionGuidance", []) or []
        insights = payload.get("migrationGuideInsights", []) or []
        if not guidance and not insights:
            return ["- status: NO_CONVERSION_GUIDANCE_RETURNED"]
        lines = []
        for item in guidance:
            if isinstance(item, dict):
                lines.append(
                    f"- {item.get('status', 'REVIEW_REQUIRED')} `{item.get('code')}`: "
                    f"{item.get('summary')}"
                )
        for item in insights:
            if isinstance(item, dict):
                lines.append(
                    f"- guide `{item.get('section')}`: {item.get('summary')}"
                )
        return lines or ["- status: NO_CONVERSION_GUIDANCE_RETURNED"]


class JavaMyBatisSpWrapperRenderer(JavaMyBatisDraftRendererBase):
    template_id = SP_WRAPPER_TEMPLATE_ID
    requested_output_type = RequestedOutputType.JAVA_MYBATIS_DRAFT.value

    def dto_path(self, context: GenerationContext) -> str:
        names = self.names(context)
        return names.source_path("model", names.dto_class_name)

    def service_path(self, context: GenerationContext) -> str:
        names = self.names(context)
        return names.source_path("service", names.service_class_name)

    def mapper_path(self, context: GenerationContext) -> str:
        names = self.names(context)
        return names.source_path("mapper", names.mapper_class_name)

    def mapper_xml_path(self, context: GenerationContext) -> str:
        return self.names(context).mapper_xml_path

    def render_dto(self, context: GenerationContext) -> str:
        names = self.names(context)
        return self.render_data_class(
            context,
            names,
            class_name=names.dto_class_name,
            object_type_label="DTO",
        )

    def render_bundle(self, context: GenerationContext) -> RenderedBundle:
        if context.generation_mode != "spWrapper":
            raise ValueError(
                "JavaMyBatisSpWrapperRenderer only supports generationMode=spWrapper. "
                "Other modes remain TODO/REVIEW_REQUIRED."
            )
        names = self.names(context)
        files = (
            DraftFile(
                path=names.source_path("model", names.dto_class_name),
                content=self.render_data_class(
                    context,
                    names,
                    class_name=names.dto_class_name,
                    object_type_label="DTO",
                ),
                artifact_type=ArtifactType.DTO_DRAFT,
            ),
            DraftFile(
                path=names.source_path("service", names.service_class_name),
                content=self.render_service(context, names),
                artifact_type=ArtifactType.SERVICE_DRAFT,
            ),
            DraftFile(
                path=names.source_path("mapper", names.mapper_class_name),
                content=self.render_mapper(context, names),
                artifact_type=ArtifactType.MAPPER_INTERFACE,
            ),
            DraftFile(
                path=names.mapper_xml_path,
                content=self.render_mapper_xml(context, names),
                artifact_type=ArtifactType.MAPPER_XML,
            ),
        )
        manifest = self._render_bundle_manifest(
            context,
            files,
            names,
            code_draft_summary=(
                "DTO / Service / Mapper / Mapper XML 초안은 artifact file inventory 를 "
                "기준으로 한다."
            ),
        )
        return RenderedBundle(
            requested_output_type=self.requested_output_type,
            manifest=manifest,
            files=files,
        )

    def _render_bundle_manifest(
        self,
        context: GenerationContext,
        files: tuple[DraftFile, ...],
        names: JavaMyBatisNames,
        *,
        code_draft_summary: str,
    ) -> RenderedArtifact:
        return RenderedArtifact(
            artifact_type=self.requested_output_type,
            title=context.sample_id or f"{context.entity_name} Java/MyBatis 초안",
            content=self.render_manifest(
                context,
                files,
                names,
                code_draft_summary=code_draft_summary,
            ),
            evidence_refs=context.evidence_refs,
            registry_refs=(
                self.assets.policy_ref,
                self.assets.template_ref(self.template_id),
            ),
            assumptions=context.evidence_assumptions,
            review_required=True,
            extra={
                "artifactTypes": [file.artifact_type.value for file in files],
                "generationMode": context.generation_mode,
                "inputSnapshotHash": context.input_snapshot_hash,
                "policyVersion": self.assets.policy_version,
                "templateVersion": self.assets.template_version(self.template_id),
            },
        )


class JavaMyBatisDtoModelRenderer(JavaMyBatisDraftRendererBase):
    template_id = DTO_MODEL_TEMPLATE_ID
    requested_output_type = RequestedOutputType.DTO_MODEL_DRAFT.value

    def render_bundle(self, context: GenerationContext) -> RenderedBundle:
        names = self.names(context)
        files = (
            DraftFile(
                path=names.source_path("model", names.dto_class_name),
                content=self.render_data_class(
                    context,
                    names,
                    class_name=names.dto_class_name,
                    object_type_label="DTO",
                ),
                artifact_type=ArtifactType.DTO_DRAFT,
            ),
            DraftFile(
                path=names.source_path("model", names.vo_class_name),
                content=self.render_data_class(
                    context,
                    names,
                    class_name=names.vo_class_name,
                    object_type_label="VO",
                ),
                artifact_type=ArtifactType.VO_DRAFT,
            ),
            DraftFile(
                path=names.source_path("model", names.model_class_name),
                content=self.render_data_class(
                    context,
                    names,
                    class_name=names.model_class_name,
                    object_type_label="Model",
                ),
                artifact_type=ArtifactType.MODEL_DRAFT,
            ),
        )
        manifest = RenderedArtifact(
            artifact_type=self.requested_output_type,
            title=context.sample_id or f"{context.entity_name} DTO/VO/Model 초안",
            content=self.render_manifest(
                context,
                files,
                names,
                code_draft_summary=(
                    "DTO / VO / Model 초안은 metadata-only field evidence 를 기준으로 한다."
                ),
            ),
            evidence_refs=context.evidence_refs,
            registry_refs=(
                self.assets.policy_ref,
                self.assets.template_ref(self.template_id),
            ),
            assumptions=context.evidence_assumptions,
            review_required=True,
            extra={
                "artifactTypes": [file.artifact_type.value for file in files],
                "generationMode": context.generation_mode,
                "inputSnapshotHash": context.input_snapshot_hash,
                "policyVersion": self.assets.policy_version,
                "templateVersion": self.assets.template_version(self.template_id),
            },
        )
        return RenderedBundle(
            requested_output_type=self.requested_output_type,
            manifest=manifest,
            files=files,
        )
