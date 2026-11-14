{% macro gtfs_zip() -%}
    {%- if not execute -%}
        {{ return('') }}
    {%- endif -%}
    {%- set root = env_var("ZTM_BRONZE_ROOT", "../data/bronze") | replace("\\", "/") -%}
    {%- set result = run_query("select max(replace(file, '\\', '/')) from glob('" ~ root ~ "/gtfs/*/*.zip')") -%}
    {%- set path = result.columns[0].values()[0] -%}
    {%- if path is none -%}
        {{ exceptions.raise_compiler_error("No GTFS zip found under " ~ root ~ "/gtfs. Run `ztm-ingest gtfs` first.") }}
    {%- endif -%}
    {{ return(path) }}
{%- endmacro %}

{% macro read_gtfs(file_name) -%}
    read_csv('zip://{{ gtfs_zip() }}/{{ file_name }}', header = true, all_varchar = true, hive_partitioning = false)
{%- endmacro %}

{% macro gtfs_time_to_seconds(column) -%}
    (cast(split_part({{ column }}, ':', 1) as integer) * 3600
     + cast(split_part({{ column }}, ':', 2) as integer) * 60
     + cast(split_part({{ column }}, ':', 3) as integer))
{%- endmacro %}
