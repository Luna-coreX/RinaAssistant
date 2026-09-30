-- The beta's telemetry (`4.0b-D05`): the day a report arrived and the report.
-- No address, no time of day. One report per installation per day.
CREATE TABLE IF NOT EXISTS reports (
    day     DATE     NOT NULL,
    install CHAR(32) NOT NULL,
    report  JSONB    NOT NULL,
    PRIMARY KEY (install, day)
);
CREATE INDEX IF NOT EXISTS reports_by_day ON reports (day);
