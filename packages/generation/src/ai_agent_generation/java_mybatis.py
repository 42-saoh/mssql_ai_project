from __future__ import annotations

from ai_agent_domain import ArtifactType, RequestedOutputType

from ai_agent_generation.artifact_types import JAVA_MYBATIS_DTO_MAPPING_BLOCKER
from ai_agent_generation.models import (
    DraftFile,
    GenerationContext,
    RenderedArtifact,
    RenderedBundle,
)
from ai_agent_generation.utils import (
    ensure_trailing_newline,
    java_imports_for_types,
    java_type_for_db_type,
    korean_entity_label,
    snake_to_lower_camel,
    upper_first,
)


class JavaMyBatisSpWrapperRenderer:
    requested_output_type = RequestedOutputType.JAVA_MYBATIS_DRAFT.value

    def render_bundle(self, context: GenerationContext) -> RenderedBundle:
        files = (
            DraftFile(
                path=self.dto_path(context),
                content=self.render_dto(context),
                artifact_type=ArtifactType.DTO_DRAFT,
            ),
            DraftFile(
                path=self.service_path(context),
                content=self.render_service(context),
                artifact_type=ArtifactType.SERVICE_DRAFT,
            ),
            DraftFile(
                path=self.mapper_path(context),
                content=self.render_mapper(context),
                artifact_type=ArtifactType.MAPPER_INTERFACE,
            ),
            DraftFile(
                path=self.mapper_xml_path(context),
                content=self.render_mapper_xml(context),
                artifact_type=ArtifactType.MAPPER_XML,
            ),
        )
        manifest = RenderedArtifact(
            artifact_type=self.requested_output_type,
            title=context.sample_id or f"{context.entity_name} Java/MyBatis draft",
            content=self.render_manifest(context, files),
            evidence_refs=context.evidence_refs,
            registry_refs=(
                "policy:project_ai_java_mybatis_generation_policy.yaml@1.0.0",
                "template:java_mybatis_sp_wrapper@0.1.0",
            ),
            assumptions=context.evidence_assumptions,
            review_required=True,
            extra={
                "artifactTypes": [file.artifact_type.value for file in files],
                "generationMode": context.generation_mode,
            },
        )
        return RenderedBundle(
            requested_output_type=self.requested_output_type,
            manifest=manifest,
            files=files,
            blockers=(JAVA_MYBATIS_DTO_MAPPING_BLOCKER,),
        )

    def dto_path(self, context: GenerationContext) -> str:
        return (
            f"src/main/java/com/pec/{context.system_code_lower}/"
            f"{context.business_code_lv1}/{context.business_code_lv2}/model/"
            f"{context.dto_class_name}.java"
        )

    def service_path(self, context: GenerationContext) -> str:
        return (
            f"src/main/java/com/pec/{context.system_code_lower}/"
            f"{context.business_code_lv1}/{context.business_code_lv2}/service/"
            f"{context.service_class_name}.java"
        )

    def mapper_path(self, context: GenerationContext) -> str:
        return (
            f"src/main/java/com/pec/{context.system_code_lower}/"
            f"{context.business_code_lv1}/{context.business_code_lv2}/mapper/"
            f"{context.mapper_class_name}.java"
        )

    def mapper_xml_path(self, context: GenerationContext) -> str:
        return (
            f"src/main/resources/mybatis/{context.system_code_lower}/mappers/"
            f"{context.business_code_lv1}/{context.business_code_lv2}/"
            f"{context.mapper_class_name}SQL.xml"
        )

    def render_manifest(self, context: GenerationContext, files: tuple[DraftFile, ...]) -> str:
        label = korean_entity_label(context.description, context.entity_name)
        source_lines = []
        for source in context.evidence_sources:
            source_lines.append(f"- {source.display_type}: `{source.name}`")
        source_lines.extend(
            [
                "- DTO 필드 정의는 테이블 컬럼과 결과 shape 에 근거함",
                "- Mapper XML 은 SP 직접 호출 wrapper 로 유지함",
            ]
        )

        generated_file_lines = [f"- `{file.path}`" for file in files]
        package_lines = [
            f"- `{context.model_package}`",
            f"- `{context.service_package}`",
            f"- `{context.mapper_package}`",
            (
                f"- `src/main/resources/mybatis/{context.system_code_lower}/mappers/"
                f"{context.business_code_lv1}/{context.business_code_lv2}`"
            ),
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
            "## generation_mode",
            f"- `{context.generation_mode}`",
            "- 사유: SP 내부 조회 로직을 SQL 로 재구성할 근거가 아직 충분하지 않음",
            "",
            "## evidence_summary",
            *source_lines,
            "",
            "## package_structure",
            *package_lines,
            "",
            "## generated_files",
            *generated_file_lines,
            "",
            "## code_draft",
            "- DTO / Service / Mapper / Mapper XML 초안은 동일 디렉터리의 `src/` 아래 파일을 기준으로 한다.",
            "",
            "## message_and_config_examples",
            f"- message key example: `biz.info.{context.entity_name_lower}.retrieve.001`",
            f"- message value example: `{label} 목록을 조회했습니다.`",
            "- application yml example:",
            "",
            "```yaml",
            f"{context.system_code_lower}:",
            "  mybatis:",
            (
                "    config: "
                f"classpath:/mybatis/{context.system_code_lower}/"
                f"mybatis-config-{context.system_code_lower}.xml"
            ),
            "```",
            "",
            "## assumptions_and_todo",
            "- REVIEW_REQUIRED: 모든 파일은 draft-only 이며 수동 검토 전 실제 프로젝트 반영 금지",
            "- TODO: 페이징 조건 파라미터 유무 확인",
            "- TODO: transaction boundary 확인 후 서비스 계층 주석 보강",
            "- TODO: controller 필요 여부 확인",
            "- TODO: exact exception/message code 확정",
            "- TODO: 향후 evidence 가 충분해지면 `spRebuild` 전환 가능성 재평가",
            "",
            "## review_checklist",
            "- [x] naming_rules_applied",
            "- [x] package_pattern_applied",
            "- [x] mapper_xml_namespace_matches_interface",
            "- [x] sql_id_matches_mapper_method",
            "- [x] evidence_included",
            "- [x] assumptions_disclosed",
            "- [x] project_exclusions_respected",
        ]
        return ensure_trailing_newline("\n".join(lines))

    def render_dto(self, context: GenerationContext) -> str:
        java_types = {java_type_for_db_type(column.db_type) for column in context.columns}
        imports = java_imports_for_types(java_types)
        label = korean_entity_label(context.description, context.entity_name)
        lines = [f"package {context.model_package};", ""]
        for import_name in imports:
            lines.append(f"import {import_name};")
        if imports:
            lines.append("")
        lines.extend(
            [
                "/**",
                f" * {label} 목록 조회 DTO 초안.",
                f" * evidence: {context.sp_name}, {context.table_name}",
                " */",
                f"public class {context.dto_class_name} {{",
                "",
            ]
        )

        for index, column in enumerate(context.columns):
            if index:
                lines.append("")
            lines.append(f"    /** {column.description or column.name} */")
            java_type = java_type_for_db_type(column.db_type)
            field_name = snake_to_lower_camel(column.name)
            lines.append(
                f"    private {java_type} {field_name};"
            )

        for column in context.columns:
            field_name = snake_to_lower_camel(column.name)
            method_suffix = upper_first(field_name)
            java_type = java_type_for_db_type(column.db_type)
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

        lines.append("}")
        return ensure_trailing_newline("\n".join(lines))

    def render_service(self, context: GenerationContext) -> str:
        label = korean_entity_label(context.description, context.entity_name)
        lines = [
            f"package {context.service_package};",
            "",
            "import java.util.List;",
            "",
            f"import {context.model_package}.{context.dto_class_name};",
            "",
            "/**",
            f" * {label} 서비스 초안.",
            " */",
            f"public interface {context.service_class_name} {{",
            "",
            "    /**",
            f"     * {label} 목록을 조회한다.",
            "     *",
            "     * @param condition 조회 조건 DTO",
            f"     * @return {label} 목록",
            "     */",
            (
                f"    List<{context.dto_class_name}> {context.service_method_name}"
                f"({context.dto_class_name} condition);"
            ),
            "}",
        ]
        return ensure_trailing_newline("\n".join(lines))

    def render_mapper(self, context: GenerationContext) -> str:
        label = korean_entity_label(context.description, context.entity_name)
        lines = [
            f"package {context.mapper_package};",
            "",
            "import java.util.List;",
            "",
            f"import {context.model_package}.{context.dto_class_name};",
            "",
            "/**",
            f" * {label} Mapper 초안.",
            " */",
            f"public interface {context.mapper_class_name} {{",
            "",
            "    /**",
            f"     * {label} 목록을 조회한다.",
            "     *",
            "     * @param condition 조회 조건 DTO",
            f"     * @return {label} 목록",
            "     */",
            (
                f"    List<{context.dto_class_name}> {context.mapper_method_name}"
                f"({context.dto_class_name} condition);"
            ),
            "}",
        ]
        return ensure_trailing_newline("\n".join(lines))

    def render_mapper_xml(self, context: GenerationContext) -> str:
        param_lines = []
        for index, param in enumerate(context.input_params):
            comma = "," if index < len(context.input_params) - 1 else ""
            field_name = snake_to_lower_camel(param.name)
            param_lines.append(f"      @{param.name} = #{{{field_name}}}{comma}")
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<!DOCTYPE mapper",
            '  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"',
            '  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">',
            f'<mapper namespace="{context.mapper_package}.{context.mapper_class_name}">',
            "",
            (
                f"  <!-- {context.mapper_class_name}.{context.mapper_method_name} "
                f"{context.author_id} -->"
            ),
            f'  <select id="{context.mapper_method_name}"',
            f'          parameterType="{context.model_package}.{context.dto_class_name}"',
            f'          resultType="{context.model_package}.{context.dto_class_name}">',
            f"    EXEC {context.sp_name}",
            *param_lines,
            "  </select>",
            "",
            "</mapper>",
        ]
        return ensure_trailing_newline("\n".join(lines))
