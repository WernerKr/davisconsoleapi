#
#    Copyright (c) 2009-2020 Tom Keffer <tkeffer@gmail.com>
#
#    See the file LICENSE.txt for your rights.
#
"""The extended wview schema."""

# =============================================================================
# This is a list containing the default schema of the archive database.  It is
# only used for initialization --- afterwards, the schema is obtained
# dynamically from the database.  Although a type may be listed here, it may
# not necessarily be supported by your weather station hardware.
# =============================================================================
# NB: This schema is specified using the WeeWX V4 "new-style" schema.
# =============================================================================
table = [('dateTime',             'INTEGER NOT NULL UNIQUE PRIMARY KEY'),
    ('usUnits',              'INTEGER NOT NULL'),
    ('interval',             'INTEGER NOT NULL'),
    ("consoleBatteryC", "REAL"),
    ("rssiC", "REAL"),
    ("consoleApiLevelC", "INTEGER"),
    ("queueKilobytesC", "INTEGER"),
    ("freeMemC", "INTEGER"),
    ("systemFreeSpaceC", "INTEGER"),
    ("chargerPluggedC", "INTEGER"),
    ("batteryPercentC", "INTEGER"),
    ("localAPIQueriesC", "INTEGER"),
    ("healthVersionC", "INTEGER"),
    ("linkUptimeC", "INTEGER"),
    ("rxKilobytesC", "INTEGER"),
    ("connectionUptimeC", "INTEGER"),
    ("osUptimeC", "INTEGER"),
    ("batteryConditionC", "INTEGER"),
    ("iFreeSpaceC", "INTEGER"),
    ("batteryCurrentC", "REAL"),
    ("batteryStatusC", "INTEGER"),
    ("databaseKilobytesC", "INTEGER"),
    ("batteryCycleCountC", "INTEGER"),
    ("bootloaderVersionC", "INTEGER"),
    ("clockSourceC", "INTEGER"),
    ("appUptimeC", "INTEGER"),
    ("batteryTempC", "INTEGER"),
    ("txKilobytesC", "INTEGER"),
    ("consoleRadioVersionC", "TEXT"),
    ("consoleSwVersionC", "TEXT"),
    ("consoleOsVersionC", "TEXT"),
    ("appTemp", "REAL"),
    ("appTemp1", "REAL"),
    ("barometer", "REAL"),
    ("batteryStatus1", "REAL"),
    ("batteryStatus2", "REAL"),
    ("batteryStatus3", "REAL"),
    ("batteryStatus4", "REAL"),
    ("batteryStatus5", "REAL"),
    ("batteryStatus6", "REAL"),
    ("batteryStatus7", "REAL"),
    ("batteryStatus8", "REAL"),
    ("cloudbase", "REAL"),
    ("co", "REAL"),
    ("co2", "REAL"),
    ("co2_Temp", "REAL"),
    ("co2_Hum", "REAL"),
    ("co2_Batt", "REAL"),
    ("consBatteryVoltage", "REAL"),
    ("dewpoint", "REAL"),
    ("dewpoint1", "REAL"),
    ("ET", "REAL"),
    ("ET_2", "REAL"),
    ("extraHumid1", "REAL"),
    ("extraHumid2", "REAL"),
    ("extraHumid3", "REAL"),
    ("extraHumid4", "REAL"),
    ("extraHumid5", "REAL"),
    ("extraHumid6", "REAL"),
    ("extraHumid7", "REAL"),
    ("extraHumid8", "REAL"),
    ("extraTemp1", "REAL"),
    ("extraTemp2", "REAL"),
    ("extraTemp3", "REAL"),
    ("extraTemp4", "REAL"),
    ("extraTemp5", "REAL"),
    ("extraTemp6", "REAL"),
    ("extraTemp7", "REAL"),
    ("extraTemp8", "REAL"),
    ("forecast", "REAL"),
    ("heatindex", "REAL"),
    ("heatindex1", "REAL"),
    ("humidex", "REAL"),
    ("humidex1", "REAL"),
    ("inDewpoint", "REAL"),
    ("inHumidity", "REAL"),
    ("inTemp", "REAL"),
    ("inTempBatteryStatus", "REAL"),
    ("leafTemp1", "REAL"),
    ("leafTemp2", "REAL"),
    ("leafWet1", "REAL"),
    ("leafWet2", "REAL"),
    ("luminosity", "REAL"),
    ("maxSolarRad", "REAL"),
    ("outHumidity", "REAL"),
    ("outTemp", "REAL"),
    ("outTempBatteryStatus", "REAL"),
    ("pm10_0", "REAL"),
    ("pm1_0", "REAL"),
    ("pm2_5", "REAL"),
    ("pressure", "REAL"),
    ("radiation", "REAL"),
    ("rain", "REAL"),
    ("rainBatteryStatus", "REAL"),
    ("rainRate", "REAL"),
    ("rxCheckPercent", "REAL"),
    ("rxCheckPercent_2", "REAL"),
    ("rxCheckPercent2", "REAL"),
    ("rxCheckPercent3", "REAL"),
    ("rxCheckPercent4", "REAL"),
    ("rxCheckPercent5", "REAL"),
    ("rxCheckPercent6", "REAL"),
    ("rxCheckPercent7", "REAL"),
    ("rxCheckPercent8", "REAL"),
    ("rxCheckPercenta", "REAL"),
    ("rxCheckPercentr", "REAL"),
    ("rxCheckPercentw", "REAL"),
    ("signal1", "REAL"),
    ("signal_2", "REAL"),
    ("signal2", "REAL"),
    ("signal3", "REAL"),
    ("signal4", "REAL"),
    ("signal5", "REAL"),
    ("signal6", "REAL"),
    ("signal7", "REAL"),
    ("signal8", "REAL"),
    ("signala", "REAL"),
    ("signalr", "REAL"),
    ("signalw", "REAL"),
    ("soilMoist1", "REAL"),
    ("soilMoist2", "REAL"),
    ("soilMoist3", "REAL"),
    ("soilMoist4", "REAL"),
    ("soilTemp1", "REAL"),
    ("soilTemp2", "REAL"),
    ("soilTemp3", "REAL"),
    ("soilTemp4", "REAL"),
    ("supplyVoltage", "REAL"),
    ("txBatteryStatus", "REAL"),
    ("THSW", "REAL"),
    ("THW", "REAL"),
    ("UV", "REAL"),
    ("windBatteryStatus", "REAL"),
    ("windchill", "REAL"),
    ("windDir", "REAL"),
    ("windGust", "REAL"),
    ("windGustDir", "REAL"),
    ("windrun", "REAL"),
    ("windSpeed", "REAL"),
    ("sunshine_hours", "REAL"),
    ("sunshine_time", "REAL"),
    ("outTemp_2", "REAL"),
    ("outHumidity_2", "REAL"),
    ("dewpoint2", "REAL"),
    ("heatindex2", "REAL"),
    ("windchill2", "REAL"),
    ("THSW_2", "REAL"),
    ("THW_2", "REAL"),
    ("outWetbulb_2", "REAL"),
    ("radiation_2", "REAL"),
    ("rain_2", "REAL"),
    ("rainBatteryStatus_2", "REAL"),
    ("rainRate_2", "REAL"),
    ("UV_2", "REAL"),
    ("windSpeed_2", "REAL"),
    ("windDir_2", "REAL"),
    ("windGust_2", "REAL"),
    ("windGustDir_2", "REAL"),
    ("txBatteryStatus_2", "REAL"),
    ("sunshineDur", "REAL"),
    ("sunshineDur_2", "REAL"),
    ("rainDur", "REAL"),
    ("rainDur_2", "REAL"),
    ("rssi", "REAL"),
    ("rssi_2", "REAL"),
    ("rssi2", "REAL"),
    ("rssi3", "REAL"),
    ("rssi4", "REAL"),
    ("rssi5", "REAL"),
    ("rssi6", "REAL"),
    ("rssi7", "REAL"),
    ("rssi8", "REAL"),
    ("rssir", "REAL"),
    ("rssiw", "REAL"),
    ("txID", "INTEGER"),
    ("txID_2", "INTEGER"),
    ("txID2", "INTEGER"),
    ("txID3", "INTEGER"),
    ("txID4", "INTEGER"),
    ("txID5", "INTEGER"),
    ("txID6", "INTEGER"),
    ("txID7", "INTEGER"),
    ("txID8", "INTEGER"),
    ("txIDr", "INTEGER"),
    ("txIDw", "INTEGER"),
    ("altimeter", "REAL"),
    ("uvBatteryStatus", "REAL"),
    ("supercapVolt", "REAL"),  # volts
    ("solarVolt", "REAL"),  # volts
    ("txBatteryVolt", "REAL"),  # volts
    ("supercapVolt_2", "REAL"),  # volts
    ("solarVolt_2", "REAL"),  # volts
    ("txBatteryVolt_2", "REAL"),  # volts
    ]

day_summaries = [(e[0], 'scalar') for e in table
                 if e[0] not in ('dateTime', 'usUnits', 'interval')] + [('wind', 'VECTOR')]

schema = {
    'table': table,
    'day_summaries' : day_summaries
}
