{% macro haversine_m(lat1, lon1, lat2, lon2) -%}
    (2 * 6371008.8 * asin(sqrt(
        pow(sin(radians(({{ lat2 }}) - ({{ lat1 }})) / 2), 2)
        + cos(radians({{ lat1 }})) * cos(radians({{ lat2 }}))
        * pow(sin(radians(({{ lon2 }}) - ({{ lon1 }})) / 2), 2)
    )))
{%- endmacro %}

{% macro bearing_deg(lat1, lon1, lat2, lon2) -%}
    ((degrees(atan2(
        sin(radians(({{ lon2 }}) - ({{ lon1 }}))) * cos(radians({{ lat2 }})),
        cos(radians({{ lat1 }})) * sin(radians({{ lat2 }}))
        - sin(radians({{ lat1 }})) * cos(radians({{ lat2 }})) * cos(radians(({{ lon2 }}) - ({{ lon1 }})))
    )) + 360) % 360)
{%- endmacro %}

{% macro angle_between_deg(a, b) -%}
    least(abs(({{ a }}) - ({{ b }})), 360 - abs(({{ a }}) - ({{ b }})))
{%- endmacro %}
