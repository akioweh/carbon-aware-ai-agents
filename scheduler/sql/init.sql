create table if not exists impacts(
    id serial primary key,
    carbon_intensity double precision,
    total_emissions double precision,
    sci double precision
);

create table if not exists jobs(
    id serial primary key,
    impact_id integer not null,
    time_stamp TIMESTAMPTZ not null,
    location_id text,
    additional_load double precision,

    constraint fk_impact
        foreign key(impact_id)
        references impacts(id)
        on delete cascade
);
