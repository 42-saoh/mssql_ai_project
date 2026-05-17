from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_agent_domain import (
    ArtifactStatus,
    ArtifactType,
    RequestedOutputType,
    SpDtoBlueprintRole,
    SpOperationModel,
    SpStatementOperation,
)

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
    draft_quality_text,
    ensure_trailing_newline,
    java_imports_for_types,
    korean_entity_label,
    snake_to_lower_camel,
    upper_first,
)

SP_WRAPPER_TEMPLATE_ID = "java_mybatis_sp_wrapper"


@dataclass(frozen=True)
class _JavaFieldSpec:
    physical_name: str
    db_type: str
    description: str
    evidence_ref: str
    role: str


@dataclass(frozen=True)
class _MapperMethodSpec:
    operation: str
    target_ref: str
    method_name: str
    evidence_refs: tuple[str, ...]
    status: str = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class _OperationFieldSpec:
    name: str
    db_type: str
    source: str
    required: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class _OperationDtoSpec:
    name: str
    role: str
    operation_ids: tuple[str, ...]
    fields: tuple[_OperationFieldSpec, ...]
    evidence_refs: tuple[str, ...]
    review_markers: tuple[str, ...]


@dataclass(frozen=True)
class _OperationMethodSpec:
    method_name: str
    operation_id: str
    operation: str
    target_ref: str
    parameter_dto: str
    parameter_name: str
    result_dto: str | None
    evidence_refs: tuple[str, ...]
    review_markers: tuple[str, ...]


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
        return ensure_trailing_newline(draft_quality_text("\n".join(lines)))

    def render_data_class(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
        *,
        class_name: str,
        object_type_label: str,
    ) -> str:
        field_specs = self._field_specs(context, names)
        java_types = {names.java_type_for_db_type(field.db_type) for field in field_specs}
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

        for index, field in enumerate(field_specs):
            if index:
                lines.append("")
            self._append_field_spec(lines, field, names)

        for field in field_specs:
            self._append_accessor_spec(lines, field, names)

        lines.append("}")
        return ensure_trailing_newline("\n".join(lines))

    def _field_specs(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
    ) -> tuple[_JavaFieldSpec, ...]:
        specs: list[_JavaFieldSpec] = []
        seen: set[str] = set()
        primary_ref = self._primary_evidence_ref(context)

        for param in context.input_params:
            field_name = names.field_name(param.name)
            if not field_name or field_name in seen:
                continue
            seen.add(field_name)
            specs.append(
                _JavaFieldSpec(
                    physical_name=param.name,
                    db_type=param.db_type,
                    description="input parameter",
                    evidence_ref=primary_ref,
                    role="INPUT_PARAM",
                )
            )

        for column in context.columns:
            field_name = names.field_name(column.name)
            if not field_name or field_name in seen:
                continue
            seen.add(field_name)
            specs.append(
                _JavaFieldSpec(
                    physical_name=column.name,
                    db_type=column.db_type,
                    description=column.description or "result field candidate",
                    evidence_ref=primary_ref,
                    role="RESULT_FIELD",
                )
            )

        for field in context.result_shape:
            field_name = names.field_name(field)
            if not field_name or field_name in seen:
                continue
            seen.add(field_name)
            specs.append(
                _JavaFieldSpec(
                    physical_name=field,
                    db_type="nvarchar",
                    description="result shape candidate",
                    evidence_ref="static.analysis.migration_guide",
                    role="RESULT_FIELD_CANDIDATE",
                )
            )

        if specs:
            return tuple(specs)
        return (
            _JavaFieldSpec(
                physical_name="review_required",
                db_type="nvarchar",
                description="REVIEW_REQUIRED: no field evidence",
                evidence_ref=primary_ref,
                role="REVIEW_REQUIRED",
            ),
        )

    def _append_field_spec(
        self,
        lines: list[str],
        field: _JavaFieldSpec,
        names: JavaMyBatisNames,
    ) -> None:
        java_type = names.java_type_for_db_type(field.db_type)
        field_name = names.field_name(field.physical_name)
        lines.append(
            f"    /** {field.role}: {field.description}; evidence={field.evidence_ref}; REVIEW_REQUIRED */"
        )
        lines.append(f"    private {java_type} {field_name};")

    def _append_accessor_spec(
        self,
        lines: list[str],
        field: _JavaFieldSpec,
        names: JavaMyBatisNames,
    ) -> None:
        field_name = names.field_name(field.physical_name)
        method_suffix = upper_first(field_name)
        java_type = names.java_type_for_db_type(field.db_type)
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

    def render_service(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames | None = None,
    ) -> str:
        names = names or self.names(context)
        label = korean_entity_label(context.description, context.entity_name)
        evidence_objects = ", ".join(source.name for source in context.evidence_sources if source.name) or "REVIEW_REQUIRED"
        method_specs = self._mapper_method_specs(context, names)
        branch_lines: list[str] = []
        for spec in method_specs:
            branch_lines.extend(
                [
                    "",
                    "    /**",
                    f"     * {spec.operation} draft for `{spec.target_ref}`.",
                    f"     * evidence: {', '.join(spec.evidence_refs) or 'REVIEW_REQUIRED'}",
                    "     * REVIEW_REQUIRED: confirm branch condition, transaction boundary, and exception policy.",
                    "     */",
                ]
            )
            if spec.operation == "SELECT":
                branch_lines.extend(
                    [
                        (
                            f"    public List<{names.dto_class_name}> {names.service_method_name}"
                            f"({names.dto_class_name} condition) {{"
                        ),
                        "        // REVIEW_REQUIRED: map SP branch semantics before production use.",
                        f"        return mapper.{spec.method_name}(condition);",
                        "    }",
                    ]
                )
            else:
                branch_lines.extend(
                    [
                        f"    public int {spec.method_name}({names.dto_class_name} command) {{",
                        "        // REVIEW_REQUIRED: write operation is a draft only; no automatic apply path.",
                        f"        return mapper.{spec.method_name}(command);",
                        "    }",
                    ]
                )
        lines = [
            f"package {names.service_package};",
            "",
            "import java.util.List;",
            "",
            f"import {names.mapper_package}.{names.mapper_class_name};",
            f"import {names.model_package}.{names.dto_class_name};",
            "",
            "/**",
            f" * {label} service draft reconstructed from bounded evidence.",
            f" * evidence objects: {evidence_objects}",
            " * REVIEW_REQUIRED: transaction boundary, branch semantics, and exception mapping need review.",
            " */",
            f"public class {names.service_class_name} {{",
            "",
            f"    private final {names.mapper_class_name} mapper;",
            "",
            f"    public {names.service_class_name}({names.mapper_class_name} mapper) {{",
            "        this.mapper = mapper;",
            "    }",
            *branch_lines,
            "}",
        ]
        return ensure_trailing_newline("\n".join(lines))
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
        return ensure_trailing_newline(draft_quality_text("\n".join(lines)))

    def render_mapper(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames | None = None,
    ) -> str:
        names = names or self.names(context)
        label = korean_entity_label(context.description, context.entity_name)
        evidence_objects = ", ".join(source.name for source in context.evidence_sources if source.name) or "REVIEW_REQUIRED"
        method_specs = self._mapper_method_specs(context, names)
        method_lines: list[str] = []
        for spec in method_specs:
            method_lines.extend(
                [
                    "",
                    "    /**",
                    f"     * {spec.operation} draft for `{spec.target_ref}`.",
                    f"     * evidence: {', '.join(spec.evidence_refs) or 'REVIEW_REQUIRED'}",
                    "     * REVIEW_REQUIRED: method granularity and parameter binding need review.",
                    "     */",
                ]
            )
            if spec.operation == "SELECT":
                method_lines.append(
                    f"    List<{names.dto_class_name}> {spec.method_name}({names.dto_class_name} condition);"
                )
            else:
                method_lines.append(
                    f"    int {spec.method_name}({names.dto_class_name} command);"
                )
        lines = [
            f"package {names.mapper_package};",
            "",
            "import java.util.List;",
            "",
            f"import {names.model_package}.{names.dto_class_name};",
            "",
            "/**",
            f" * {label} Mapper draft reconstructed from DML evidence.",
            f" * evidence objects: {evidence_objects}",
            " * REVIEW_REQUIRED: Mapper XML namespace/sql id and SQL clauses need review.",
            " */",
            f"public interface {names.mapper_class_name} {{",
            *method_lines,
            "}",
        ]
        return ensure_trailing_newline("\n".join(lines))
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
        return ensure_trailing_newline(draft_quality_text("\n".join(lines)))

    def render_mapper_xml(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames | None = None,
    ) -> str:
        names = names or self.names(context)
        if context.generation_mode == "spWrapper":
            return self._render_sp_wrapper_mapper_xml(context, names)

        evidence_objects = ", ".join(source.name for source in context.evidence_sources if source.name) or "REVIEW_REQUIRED"
        statement_lines: list[str] = []
        for spec in self._mapper_method_specs(context, names):
            statement_lines.extend(self._mapper_xml_statement_lines(spec, names))
            statement_lines.append("")
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<!DOCTYPE mapper",
            '  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"',
            '  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">',
            f'<mapper namespace="{names.mapper_namespace}">',
            "",
            f"  <!-- evidence objects: {evidence_objects}; REVIEW_REQUIRED: draft SQL only. -->",
            "",
            *statement_lines,
            "</mapper>",
        ]
        return ensure_trailing_newline("\n".join(lines))
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
        return ensure_trailing_newline(draft_quality_text("\n".join(lines)))

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

    def _migration_guide(self, context: GenerationContext) -> dict[str, Any]:
        payload = context.value("migrationGuide", {}) or {}
        return dict(payload) if isinstance(payload, Mapping) else {}

    def _primary_evidence_ref(self, context: GenerationContext) -> str:
        guide = self._migration_guide(context)
        refs = guide.get("evidence_refs")
        if isinstance(refs, list) and refs and isinstance(refs[0], Mapping):
            return str(refs[0].get("id") or "ev_request_target")
        if context.evidence_sources:
            return context.evidence_sources[0].name
        return "REVIEW_REQUIRED"

    def _mapper_method_specs(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
    ) -> tuple[_MapperMethodSpec, ...]:
        guide = self._migration_guide(context)
        specs: list[_MapperMethodSpec] = []
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(guide.get("dml_matrix", []) or [], start=1):
            if not isinstance(item, Mapping):
                continue
            operation = str(item.get("operation") or "REVIEW_REQUIRED").upper()
            target_ref = str(item.get("target_ref") or context.table_name or "REVIEW_REQUIRED")
            key = (operation, target_ref)
            if key in seen:
                continue
            seen.add(key)
            evidence_refs = tuple(
                str(ref) for ref in (item.get("evidence_refs") or []) if str(ref)
            ) or ("static.analysis.migration_guide",)
            specs.append(
                _MapperMethodSpec(
                    operation=operation,
                    target_ref=target_ref,
                    method_name=self._mapper_method_name(operation, target_ref, names, index),
                    evidence_refs=evidence_refs,
                    status=str(item.get("status") or "REVIEW_REQUIRED"),
                )
            )
        if specs:
            return tuple(specs)
        return (
            _MapperMethodSpec(
                operation="SELECT",
                target_ref=context.table_name or context.sp_name or "REVIEW_REQUIRED",
                method_name=names.mapper_method_name,
                evidence_refs=(self._primary_evidence_ref(context),),
            ),
        )

    def _mapper_method_name(
        self,
        operation: str,
        target_ref: str,
        names: JavaMyBatisNames,
        index: int,
    ) -> str:
        if operation == "SELECT":
            return names.mapper_method_name
        target_name = target_ref.rsplit(".", 1)[-1]
        suffix = upper_first(names.field_name(target_name)) or f"Target{index}"
        return f"{operation.lower()}{names.context.entity_name}{suffix}"

    def _mapper_xml_statement_lines(
        self,
        spec: _MapperMethodSpec,
        names: JavaMyBatisNames,
    ) -> list[str]:
        evidence = ", ".join(spec.evidence_refs) or "REVIEW_REQUIRED"
        parameter_type = f"{names.model_package}.{names.dto_class_name}"
        if spec.operation == "SELECT":
            return [
                f"  <!-- evidence: {evidence}; REVIEW_REQUIRED: SELECT columns/JOIN/WHERE need confirmation. -->",
                f'  <select id="{spec.method_name}"',
                f'          parameterType="{parameter_type}"',
                f'          resultType="{parameter_type}">',
                f"    {self._sql_skeleton(spec.operation, spec.target_ref)}",
                "  </select>",
            ]
        tag = spec.operation.lower() if spec.operation in {"INSERT", "UPDATE", "DELETE"} else "update"
        return [
            f"  <!-- evidence: {evidence}; REVIEW_REQUIRED: {spec.operation} statement is a sanitized skeleton only. -->",
            f'  <{tag} id="{spec.method_name}" parameterType="{parameter_type}">',
            f"    {self._sql_skeleton(spec.operation, spec.target_ref)}",
            f"  </{tag}>",
        ]

    def _sql_skeleton(self, operation: str, target_ref: str) -> str:
        if operation == "SELECT":
            return (
                f"SELECT /* REVIEW_REQUIRED columns */ FROM {target_ref} "
                "WHERE /* REVIEW_REQUIRED predicates */"
            )
        if operation == "INSERT":
            return (
                f"INSERT INTO {target_ref} (/* REVIEW_REQUIRED columns */) "
                "VALUES (/* REVIEW_REQUIRED values */)"
            )
        if operation == "UPDATE":
            return (
                f"UPDATE {target_ref} SET /* REVIEW_REQUIRED assignments */ "
                "WHERE /* REVIEW_REQUIRED predicates */"
            )
        if operation == "DELETE":
            return f"DELETE FROM {target_ref} WHERE /* REVIEW_REQUIRED predicates */"
        if operation == "MERGE":
            return (
                f"MERGE {target_ref} USING /* REVIEW_REQUIRED source */ "
                "ON /* REVIEW_REQUIRED match */"
            )
        return f"/* REVIEW_REQUIRED {operation} skeleton for {target_ref} */"

    def _render_sp_wrapper_mapper_xml(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
    ) -> str:
        evidence_objects = ", ".join(source.name for source in context.evidence_sources if source.name) or "REVIEW_REQUIRED"
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
            f"  <!-- evidence objects: {evidence_objects}; REVIEW_REQUIRED: SP wrapper draft only. -->",
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
        if context.generation_mode not in {"spWrapper", "spRebuild", "evidenceReconstructed"}:
            raise ValueError(
                "JavaMyBatisSpWrapperRenderer supports generationMode=spWrapper, "
                "spRebuild, or evidenceReconstructed."
            )
        names = self.names(context)
        operation_model = self._operation_model(context)
        if operation_model is not None:
            return self._render_operation_model_bundle(context, names, operation_model)

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

    def _operation_model(self, context: GenerationContext) -> SpOperationModel | None:
        payload = context.operation_model
        if not payload:
            return None
        return SpOperationModel.model_validate(payload)

    def _render_operation_model_bundle(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
        operation_model: SpOperationModel,
    ) -> RenderedBundle:
        dto_specs = self._operation_dto_specs(operation_model)
        method_specs = self._operation_method_specs(operation_model, dto_specs)
        dto_files = tuple(
            DraftFile(
                path=names.source_path("model", spec.name),
                content=self._render_operation_dto(context, names, spec),
                artifact_type=ArtifactType.DTO_DRAFT,
            )
            for spec in dto_specs
        )
        files = (
            *dto_files,
            DraftFile(
                path=names.source_path("service", names.service_class_name),
                content=self._render_operation_service(context, names, method_specs),
                artifact_type=ArtifactType.SERVICE_DRAFT,
            ),
            DraftFile(
                path=names.source_path("mapper", names.mapper_class_name),
                content=self._render_operation_mapper(context, names, method_specs),
                artifact_type=ArtifactType.MAPPER_INTERFACE,
            ),
            DraftFile(
                path=names.mapper_xml_path,
                content=self._render_operation_mapper_xml(context, names, method_specs),
                artifact_type=ArtifactType.MAPPER_XML,
            ),
        )
        manifest = self._render_bundle_manifest(
            context,
            files,
            names,
            code_draft_summary=(
                "operationModel.dtoBlueprints 기준으로 DTO_DRAFT를 multi-file bundle로 "
                "생성하고 Service / Mapper / Mapper XML은 단일 draft 파일로 생성했다."
            ),
        )
        return RenderedBundle(
            requested_output_type=self.requested_output_type,
            manifest=manifest,
            files=files,
        )

    def _operation_dto_specs(
        self,
        operation_model: SpOperationModel,
    ) -> tuple[_OperationDtoSpec, ...]:
        specs: list[_OperationDtoSpec] = []
        for dto in operation_model.dto_blueprints:
            fields = tuple(
                _OperationFieldSpec(
                    name=field.name,
                    db_type=field.db_type,
                    source=field.source,
                    required=field.required,
                    evidence_refs=tuple(field.evidence_refs),
                )
                for field in dto.fields
            )
            specs.append(
                _OperationDtoSpec(
                    name=dto.name,
                    role=self._enum_value(dto.role),
                    operation_ids=tuple(dto.operation_ids),
                    fields=fields,
                    evidence_refs=tuple(dto.evidence_refs),
                    review_markers=tuple(dto.review_markers),
                )
            )
        return tuple(specs)

    def _operation_method_specs(
        self,
        operation_model: SpOperationModel,
        dto_specs: tuple[_OperationDtoSpec, ...],
    ) -> tuple[_OperationMethodSpec, ...]:
        dto_by_name = {dto.name: dto for dto in dto_specs}
        statement_by_id = {
            statement.statement_id: statement
            for statement in operation_model.statement_evidence
        }
        method_specs: list[_OperationMethodSpec] = []
        seen_method_names: set[str] = set()

        for operation in operation_model.operations:
            referenced_dtos = [
                dto_by_name[name]
                for name in operation.dto_blueprint_refs
                if name in dto_by_name
            ]
            statements = [
                statement_by_id[statement_id]
                for statement_id in operation.statement_refs
                if statement_id in statement_by_id
            ]
            result_dto = next(
                (dto for dto in referenced_dtos if dto.role == SpDtoBlueprintRole.RESULT.value),
                None,
            )
            query_dto = next(
                (dto for dto in referenced_dtos if dto.role == SpDtoBlueprintRole.QUERY.value),
                None,
            )
            if query_dto is not None and result_dto is not None:
                statement = self._statement_for_dto(query_dto, statements)
                method_specs.append(
                    self._operation_method_spec(
                        method_name=self._unique_method_name(
                            operation.operation_id,
                            seen_method_names,
                        ),
                        operation_id=operation.operation_id,
                        dto=query_dto,
                        statement=statement,
                        fallback_target_ref=operation_model.target_ref,
                        result_dto=result_dto.name,
                        operation_review_markers=tuple(operation.risk_markers),
                    )
                )

            for dto in referenced_dtos:
                if dto.role not in {
                    SpDtoBlueprintRole.COMMAND.value,
                    SpDtoBlueprintRole.BATCH_ITEM.value,
                    SpDtoBlueprintRole.CALL_REQUEST.value,
                }:
                    continue
                statement = self._statement_for_dto(dto, statements)
                method_specs.append(
                    self._operation_method_spec(
                        method_name=self._unique_method_name(
                            self._method_name_from_dto(dto.name),
                            seen_method_names,
                        ),
                        operation_id=operation.operation_id,
                        dto=dto,
                        statement=statement,
                        fallback_target_ref=operation_model.target_ref,
                        result_dto=None,
                        operation_review_markers=tuple(operation.risk_markers),
                    )
                )

        return tuple(method_specs)

    def _operation_method_spec(
        self,
        *,
        method_name: str,
        operation_id: str,
        dto: _OperationDtoSpec,
        statement: Any | None,
        fallback_target_ref: str,
        result_dto: str | None,
        operation_review_markers: tuple[str, ...],
    ) -> _OperationMethodSpec:
        evidence_refs = list(dto.evidence_refs)
        review_markers = list(dto.review_markers)
        operation = "REVIEW_REQUIRED"
        target_ref = fallback_target_ref
        if statement is not None:
            operation = self._enum_value(statement.operation)
            target_ref = statement.target_ref
            evidence_refs.extend(statement.evidence_refs)
            review_markers.extend(statement.review_markers)

        return _OperationMethodSpec(
            method_name=method_name,
            operation_id=operation_id,
            operation=operation,
            target_ref=target_ref,
            parameter_dto=dto.name,
            parameter_name=self._parameter_name_for_role(dto.role),
            result_dto=result_dto,
            evidence_refs=self._dedupe(evidence_refs) or ("REVIEW_REQUIRED",),
            review_markers=(
                self._dedupe([*review_markers, *operation_review_markers])
                or ("REVIEW_REQUIRED",)
            ),
        )

    def _statement_for_dto(self, dto: _OperationDtoSpec, statements: list[Any]) -> Any | None:
        if not statements:
            return None
        preferred_operations = self._preferred_statement_operations(dto.role)
        dto_tokens = self._dto_name_tokens(dto.name)

        def score(statement: Any) -> tuple[int, int, int]:
            operation = self._enum_value(statement.operation)
            haystack = " ".join(
                [
                    statement.statement_id,
                    statement.phase,
                    statement.target_ref,
                ]
            ).lower()
            operation_score = 10 if operation in preferred_operations else 0
            token_score = sum(1 for token in dto_tokens if token and token in haystack)
            compute_penalty = -5 if operation == SpStatementOperation.COMPUTE.value else 0
            return (operation_score, token_score, compute_penalty)

        return max(statements, key=score)

    def _preferred_statement_operations(self, role: str) -> set[str]:
        if role in {SpDtoBlueprintRole.QUERY.value, SpDtoBlueprintRole.RESULT.value}:
            return {SpStatementOperation.SELECT.value}
        if role == SpDtoBlueprintRole.CALL_REQUEST.value:
            return {SpStatementOperation.EXECUTE.value}
        if role == SpDtoBlueprintRole.BATCH_ITEM.value:
            return {
                SpStatementOperation.INSERT.value,
                SpStatementOperation.UPDATE.value,
            }
        return {
            SpStatementOperation.INSERT.value,
            SpStatementOperation.UPDATE.value,
            SpStatementOperation.DELETE.value,
            SpStatementOperation.EXECUTE.value,
        }

    def _render_operation_dto(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
        spec: _OperationDtoSpec,
    ) -> str:
        java_types = {names.java_type_for_db_type(field.db_type) for field in spec.fields}
        imports = java_imports_for_types(java_types)
        label = korean_entity_label(context.description, context.entity_name)
        evidence = ", ".join(spec.evidence_refs) or "REVIEW_REQUIRED"
        review_markers = ", ".join(spec.review_markers) or "REVIEW_REQUIRED"
        lines = [f"package {names.model_package};", ""]
        for import_name in imports:
            lines.append(f"import {import_name};")
        if imports:
            lines.append("")
        lines.extend(
            [
                "/**",
                f" * {label} {spec.role} DTO draft for operationModel.",
                f" * operations: {', '.join(spec.operation_ids) or 'REVIEW_REQUIRED'}",
                f" * evidence: {evidence}",
                f" * REVIEW_REQUIRED: {review_markers}",
                " */",
                f"public class {spec.name} {{",
                "",
            ]
        )
        for index, field in enumerate(spec.fields):
            if index:
                lines.append("")
            required = "required" if field.required else "optional"
            field_evidence = ", ".join(field.evidence_refs) or "REVIEW_REQUIRED"
            java_type = names.java_type_for_db_type(field.db_type)
            lines.append(
                f"    /** {required}; source={field.source}; evidence={field_evidence}; REVIEW_REQUIRED */"
            )
            lines.append(f"    private {java_type} {field.name};")

        for field in spec.fields:
            method_suffix = upper_first(field.name)
            java_type = names.java_type_for_db_type(field.db_type)
            lines.extend(
                [
                    "",
                    f"    public {java_type} get{method_suffix}() {{",
                    f"        return {field.name};",
                    "    }",
                    "",
                    f"    public void set{method_suffix}({java_type} {field.name}) {{",
                    f"        this.{field.name} = {field.name};",
                    "    }",
                ]
            )
        lines.append("}")
        return ensure_trailing_newline("\n".join(lines))

    def _render_operation_service(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
        method_specs: tuple[_OperationMethodSpec, ...],
    ) -> str:
        label = korean_entity_label(context.description, context.entity_name)
        evidence_objects = ", ".join(
            source.name for source in context.evidence_sources if source.name
        ) or "REVIEW_REQUIRED"
        lines = [f"package {names.service_package};", ""]
        if any(method.result_dto for method in method_specs):
            lines.extend(["import java.util.List;", ""])
        lines.append(f"import {names.mapper_package}.{names.mapper_class_name};")
        for dto_name in self._used_dto_names(method_specs):
            lines.append(f"import {names.model_package}.{dto_name};")
        lines.extend(
            [
                "",
                "/**",
                f" * {label} service draft generated from SpOperationModel.",
                f" * evidence objects: {evidence_objects}",
                " * REVIEW_REQUIRED: transaction boundary, branch semantics, and exception policy.",
                " */",
                f"public class {names.service_class_name} {{",
                "",
                f"    private final {names.mapper_class_name} mapper;",
                "",
                f"    public {names.service_class_name}({names.mapper_class_name} mapper) {{",
                "        this.mapper = mapper;",
                "    }",
            ]
        )
        for method in method_specs:
            return_type = (
                f"List<{method.result_dto}>" if method.result_dto is not None else "int"
            )
            evidence = ", ".join(method.evidence_refs) or "REVIEW_REQUIRED"
            review = ", ".join(method.review_markers) or "REVIEW_REQUIRED"
            lines.extend(
                [
                    "",
                    "    /**",
                    f"     * {method.operation_id} / {method.operation} draft for `{method.target_ref}`.",
                    f"     * evidence: {evidence}",
                    f"     * REVIEW_REQUIRED: {review}",
                    "     */",
                    (
                        f"    public {return_type} {method.method_name}"
                        f"({method.parameter_dto} {method.parameter_name}) {{"
                    ),
                    "        // REVIEW_REQUIRED: map SP branch semantics before production use.",
                    f"        return mapper.{method.method_name}({method.parameter_name});",
                    "    }",
                ]
            )
        lines.append("}")
        return ensure_trailing_newline("\n".join(lines))

    def _render_operation_mapper(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
        method_specs: tuple[_OperationMethodSpec, ...],
    ) -> str:
        label = korean_entity_label(context.description, context.entity_name)
        evidence_objects = ", ".join(
            source.name for source in context.evidence_sources if source.name
        ) or "REVIEW_REQUIRED"
        lines = [f"package {names.mapper_package};", ""]
        if any(method.result_dto for method in method_specs):
            lines.extend(["import java.util.List;", ""])
        for dto_name in self._used_dto_names(method_specs):
            lines.append(f"import {names.model_package}.{dto_name};")
        lines.extend(
            [
                "",
                "/**",
                f" * {label} mapper draft generated from SpOperationModel.",
                f" * evidence objects: {evidence_objects}",
                " * REVIEW_REQUIRED: Mapper XML SQL clauses and binding policy.",
                " */",
                f"public interface {names.mapper_class_name} {{",
            ]
        )
        for method in method_specs:
            return_type = (
                f"List<{method.result_dto}>" if method.result_dto is not None else "int"
            )
            evidence = ", ".join(method.evidence_refs) or "REVIEW_REQUIRED"
            review = ", ".join(method.review_markers) or "REVIEW_REQUIRED"
            lines.extend(
                [
                    "",
                    "    /**",
                    f"     * {method.operation_id} / {method.operation} draft for `{method.target_ref}`.",
                    f"     * evidence: {evidence}",
                    f"     * REVIEW_REQUIRED: {review}",
                    "     */",
                    (
                        f"    {return_type} {method.method_name}"
                        f"({method.parameter_dto} {method.parameter_name});"
                    ),
                ]
            )
        lines.append("}")
        return ensure_trailing_newline("\n".join(lines))

    def _render_operation_mapper_xml(
        self,
        context: GenerationContext,
        names: JavaMyBatisNames,
        method_specs: tuple[_OperationMethodSpec, ...],
    ) -> str:
        evidence_objects = ", ".join(
            source.name for source in context.evidence_sources if source.name
        ) or "REVIEW_REQUIRED"
        statement_lines: list[str] = []
        for method in method_specs:
            statement_lines.extend(self._operation_mapper_xml_statement(method, names))
            statement_lines.append("")
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<!DOCTYPE mapper",
            '  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"',
            '  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">',
            f'<mapper namespace="{names.mapper_namespace}">',
            "",
            (
                f"  <!-- evidence objects: {evidence_objects}; "
                "REVIEW_REQUIRED: operationModel SQL skeleton only. -->"
            ),
            "",
            *statement_lines,
            "</mapper>",
        ]
        return ensure_trailing_newline("\n".join(lines))

    def _operation_mapper_xml_statement(
        self,
        method: _OperationMethodSpec,
        names: JavaMyBatisNames,
    ) -> list[str]:
        evidence = ", ".join(method.evidence_refs) or "REVIEW_REQUIRED"
        review = ", ".join(method.review_markers) or "REVIEW_REQUIRED"
        parameter_type = f"{names.model_package}.{method.parameter_dto}"
        if method.result_dto is not None:
            result_type = f"{names.model_package}.{method.result_dto}"
            return [
                (
                    f"  <!-- operationId: {method.operation_id}; evidence: {evidence}; "
                    f"REVIEW_REQUIRED: {review} -->"
                ),
                f'  <select id="{method.method_name}"',
                f'          parameterType="{parameter_type}"',
                f'          resultType="{result_type}">',
                f"    {self._sql_skeleton(method.operation, method.target_ref)}",
                "  </select>",
            ]
        tag = (
            method.operation.lower()
            if method.operation in {"INSERT", "UPDATE", "DELETE"}
            else "update"
        )
        return [
            (
                f"  <!-- operationId: {method.operation_id}; evidence: {evidence}; "
                f"REVIEW_REQUIRED: {review} -->"
            ),
            f'  <{tag} id="{method.method_name}" parameterType="{parameter_type}">',
            f"    {self._sql_skeleton(method.operation, method.target_ref)}",
            f"  </{tag}>",
        ]

    def _used_dto_names(
        self,
        method_specs: tuple[_OperationMethodSpec, ...],
    ) -> tuple[str, ...]:
        names: list[str] = []
        for method in method_specs:
            names.append(method.parameter_dto)
            if method.result_dto is not None:
                names.append(method.result_dto)
        return self._dedupe(names)

    def _method_name_from_dto(self, dto_name: str) -> str:
        stem = dto_name
        for suffix in (
            "CallRequest",
            "BatchItem",
            "Command",
            "Criteria",
            "Request",
            "Row",
        ):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return stem[:1].lower() + stem[1:] if stem else "reviewRequired"

    def _parameter_name_for_role(self, role: str) -> str:
        if role == SpDtoBlueprintRole.QUERY.value:
            return "condition"
        if role == SpDtoBlueprintRole.BATCH_ITEM.value:
            return "item"
        if role == SpDtoBlueprintRole.CALL_REQUEST.value:
            return "request"
        return "command"

    def _unique_method_name(self, method_name: str, seen: set[str]) -> str:
        if method_name not in seen:
            seen.add(method_name)
            return method_name
        index = 2
        while f"{method_name}{index}" in seen:
            index += 1
        unique = f"{method_name}{index}"
        seen.add(unique)
        return unique

    def _dto_name_tokens(self, dto_name: str) -> tuple[str, ...]:
        tokens: list[str] = []
        current = ""
        for char in dto_name:
            if char.isupper() and current:
                tokens.append(current.lower())
                current = char
            else:
                current += char
        if current:
            tokens.append(current.lower())
        ignored = {
            "bond",
            "command",
            "criteria",
            "row",
            "batch",
            "item",
            "request",
        }
        return tuple(token for token in tokens if token not in ignored)

    def _enum_value(self, value: Any) -> str:
        return str(getattr(value, "value", value))

    def _dedupe(self, values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return tuple(deduped)

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
