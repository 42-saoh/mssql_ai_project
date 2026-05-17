# P36D Java MyBatis Business Logic Renderer

## Role

template_engineer

## Context

Use `spec/eval/p36_output_renewal_contract.yaml`, the migration-guide payload, and the Java/MyBatis generation policy.

## Task

Connect `spRebuild` or `evidenceReconstructed` generation mode to Java/MyBatis renderers:

- `DTO.java`: include input parameters and result field candidates with evidence refs.
- `Service.java`: draft service class with business branch flow, transaction/exception caveats, and `REVIEW_REQUIRED`.
- `Mapper.java`: branch/DML-specific mapper methods.
- `MapperSQL.xml`: evidence-backed SQL skeletons with `REVIEW_REQUIRED` comments for uncertain SQL clauses.

## Constraints

- Do not generate production-ready code claims.
- Do not create VO/Model/DDL artifacts.
- Do not store full SP definitions.
- Use deterministic renderer logic before LLM inference.

## Acceptance

- Unit/golden/eval tests cover evidence-backed Java/MyBatis draft content.
- Generated bundle manifest contains only DTO, Service, Mapper interface, and Mapper XML.
