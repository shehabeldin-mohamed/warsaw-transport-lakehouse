with polls as (
    select *
    from read_json(
        '{{ env_var("ZTM_BRONZE_ROOT", "../data/bronze") }}/vehicle_positions/*/*/*/*.json',
        hive_partitioning = true,  -- adds the type=, date= and hour= folders as columns
        filename = true,
        columns = {
            '_meta': 'STRUCT(received_at_utc TIMESTAMPTZ)',
            'payload': 'STRUCT("Lines" VARCHAR, "Brigade" VARCHAR, "VehicleNumber" VARCHAR,
                               "Lat" DOUBLE, "Lon" DOUBLE, "Time" VARCHAR)[]'
        }
    )
),

records as (
    select
        polls.type as vehicle_type,
        polls._meta.received_at_utc as received_at_utc,
        polls.filename as source_file,
        unnest(polls.payload) as r  -- one row per record in the payload list
    from polls
),

typed as (
    select
        vehicle_type,
        r."VehicleNumber" as vehicle_number,
        r."Lines" as line,
        r."Brigade" as brigade,
        r."Lat" as lat,
        r."Lon" as lon,
        timezone('Europe/Warsaw', strptime(r."Time", '%Y-%m-%d %H:%M:%S')) as reported_at_utc,
        received_at_utc,
        source_file
    from records
)

select
    *,
    received_at_utc - reported_at_utc as report_age,
    received_at_utc - reported_at_utc > interval 5 minute as is_stale,
    lat between 51.9 and 52.5 and lon between 20.6 and 21.4 as is_in_warsaw_area
from typed
qualify row_number() over (
    partition by vehicle_type, vehicle_number, reported_at_utc
    order by received_at_utc
) = 1
