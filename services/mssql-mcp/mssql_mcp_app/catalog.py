from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    read_only: bool = True


TOOL_CATALOG = [
    ToolSpec("get_procedure_definition", "Return stored procedure definition metadata."),
    ToolSpec("get_procedure_parameters", "Return stored procedure parameter metadata."),
    ToolSpec("get_procedure_dependencies", "Return stored procedure dependency metadata."),
    ToolSpec("get_related_db_objects", "Return related table/view/function objects."),
    ToolSpec("get_table_schema", "Return columns and data types for a table."),
    ToolSpec("get_table_constraints", "Return PK/FK/UQ/CHECK constraints for a table."),
    ToolSpec("get_table_indexes", "Return index metadata for a table."),
    ToolSpec("get_extended_properties", "Return descriptions and logical names."),
    ToolSpec("get_view_definition", "Return view definition metadata."),
    ToolSpec("get_function_definition", "Return function definition metadata."),
    ToolSpec("search_tables", "Search tables by name, description, or column structure."),
    ToolSpec("search_columns", "Search columns by physical/logical name or description."),
    ToolSpec("find_similar_tables", "Recommend similar tables using metadata signals."),
]
