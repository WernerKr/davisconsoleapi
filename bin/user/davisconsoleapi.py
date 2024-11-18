#!/usr/bin/python3
"""

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.


weewx module that records information from a Davis Console weather station using
the v2 API.

version:
01 initial release
02 add dewpoint1, heatindex1, wetbulb1 for second Vantage/VUE
03 add DAvis Airlink senosr, the Airlink health data are not stored in the database! 

Settings in weewx.conf:

[StdReport]
    [[DavisConsole]]
        HTML_ROOT = /var/www/html/weewx
        lang = en
        enable = true
        skin = console

    [[DavisHealthConsole]]
        HTML_ROOT = /var/www/html/weewx/healthc
        lang = en
        enable = true
        skin = healthc

[DataBindings]
    [[wx_binding]]
        database = davisconsoleapi_sqlite
        table_name = archive
        manager = weewx.manager.DaySummaryManager
        schema = schemas.wview_davisconsoleapi.schema

[Databases]
    [[davisconsoleapi_sqlite]]
        database_type = SQLite
        database_name = davisconsole.sdb

[Engine]
    [[Services]]
        #data_services = user.davisconsoleapi.DavisConsoleAPI,

[DavisConsoleAPI]
    driver = user.davisconsoleapi
    station_id = 123456
    polling_interval = 300 # 300 = default minimum 60 sec 
    api_key = abcdefghijklmnopqrstuvwzyx123456
    api_secret = 123456abcdefghijklmnopqrstuvwxyz
    txid_iss = 1
    txid_iss2 = None
    txid_leaf_soil = None
    txid_leaf = None
    txid_soil = None
    txid_extra1 = None      # yet not supported by Davis Console
    txid_extra2 = None      # yet not supported by Davis Console
    txid_extra3 = None      # yet not supported by Davis Console
    txid_extra4 = None      # yet not supported by Davis Console
    txid_rain = None        # seems that yet not supported by Davis Console
    txid_wind = None        # supported ?
    airlink = 0 		# Airlink Sensor available?
    packet_log = 0

#packet_log = -1 -> current rain data
#packet_log = 0 -> none logging
#packet_log = 1 -> check new Archive and Rain
#packet_log = 2 -> current console (bar/temp/hum) packets
#packet_log = 3 -> current ISS/VuE packets
#packet_log = 4 -> current leaf soil packets
#packet_log = 5 -> current extra_data1..4 packets
#packet_log = 6 -> current rain and/or wind packets
#packet_log = 7 -> current iss2 or vue2 packets
#packet_log = 8 -> current health packets
#packet_log = 9 -> all current packets


[Accumulator]
   [[consoleRadioVersionC]]
        accumulator = firstlast
        extractor = last
   [[consoleSwVersionC]]
        accumulator = firstlast
        extractor = last
   [[consoleOsVersionC]]
        accumulator = firstlast
        extractor = last


"""

from __future__ import with_statement
from __future__ import absolute_import
from __future__ import print_function

import json
import requests
import time
import hashlib
import hmac

import weewx
import weewx.units
import datetime
import weewx.drivers
from weewx.engine import StdService

import weeutil.weeutil

try:
    # Test for new-style weewx logging by trying to import weeutil.logger
    import weeutil.logger
    import logging

    log = logging.getLogger(__name__)

    def logdbg(msg):
        """Log debug messages"""
        log.debug(msg)

    def loginf(msg):
        """Log info messages"""
        log.info(msg)

    def logerr(msg):
        """Log error messages"""
        log.error(msg)


except ImportError:
    # Old-style weewx logging
    import syslog

    def logmsg(level, msg):
        """Log messages"""
        syslog.syslog(level, "DavisConsoleAPI: %s:" % msg)

    def logdbg(msg):
        """Log debug messages"""
        logmsg(syslog.LOG_DEBUG, msg)

    def loginf(msg):
        """Log info messages"""
        logmsg(syslog.LOG_INFO, msg)

    def logerr(msg):
        """Log error messages"""
        logmsg(syslog.LOG_ERR, msg)


DRIVER_NAME = "DavisConsoleAPI"
DRIVER_VERSION = "0.42"

if weewx.__version__ < "4":
    raise weewx.UnsupportedFeature("weewx 4 is required, found %s" % weewx.__version__)

weewx.units.USUnits["group_decibels"] = "decibels"
weewx.units.MetricUnits["group_decibels"] = "decibels"
weewx.units.MetricWXUnits["group_decibels"] = "decibels"
weewx.units.default_unit_format_dict["decibels"] = "%.1f"
weewx.units.default_unit_label_dict["decibels"] = " dBm"

weewx.units.USUnits["group_string"] = "string"
weewx.units.MetricUnits["group_string"] = "string"
weewx.units.MetricWXUnits["group_string"] = "string"
weewx.units.default_unit_label_dict["string"] = ""
weewx.units.default_unit_format_dict["string"] = "%s"

weewx.units.USUnits["group_millivolts"] = "millivolts"
weewx.units.MetricUnits["group_millivolts"] = "millivolts"
weewx.units.MetricWXUnits["group_millivolts"] = "millivolts"
weewx.units.default_unit_format_dict["millivolts"] = "%d"
weewx.units.default_unit_label_dict["millivolts"] = " mV"

weewx.units.USUnits["group_ampere"] = "ampere"
weewx.units.MetricUnits["group_ampere"] = "ampere"
weewx.units.MetricWXUnits["group_ampere"] = "ampere"
weewx.units.default_unit_format_dict["ampere"] = "%.3f"
weewx.units.default_unit_label_dict["ampere"] = " A"

weewx.units.obs_group_dict["consoleBatteryC"] = "group_millivolts"
weewx.units.obs_group_dict["rssiC"] = "group_decibels"
weewx.units.obs_group_dict["consoleApiLevelC"] = "group_count"
weewx.units.obs_group_dict["queueKilobytesC"] = "group_count"
weewx.units.obs_group_dict["freeMemC"] = "group_count"
weewx.units.obs_group_dict["systemFreeSpaceC"] = "group_count"
weewx.units.obs_group_dict["chargerPluggedC"] = "group_count"
weewx.units.obs_group_dict["batteryPercentC"] = "group_percent"
weewx.units.obs_group_dict["localAPIQueriesC"] = "group_count"
weewx.units.obs_group_dict["healthVersionC"] = "group_count"
weewx.units.obs_group_dict["linkUptimeC"] = "group_deltatime"
weewx.units.obs_group_dict["rxKilobytesC"] = "group_count"

weewx.units.obs_group_dict["connectionUptimeC"] = "group_deltatime"
weewx.units.obs_group_dict["osUptimeC"] = "group_deltatime"
weewx.units.obs_group_dict["batteryConditionC"] = "group_count"
weewx.units.obs_group_dict["iFreeSpaceC"] = "group_count"
weewx.units.obs_group_dict["batteryCurrentC"] = "group_ampere"
weewx.units.obs_group_dict["batteryStatusC"] = "group_count"
weewx.units.obs_group_dict["databaseKilobytesC"] = "group_count"
weewx.units.obs_group_dict["batteryCycleCountC"] = "group_count"
weewx.units.obs_group_dict["bootloaderVersionC"] = "group_count"
weewx.units.obs_group_dict["clockSourceC"] = "group_count"
weewx.units.obs_group_dict["appUptimeC"] = "group_deltatime"
weewx.units.obs_group_dict["batteryTempC"] = "group_count"
weewx.units.obs_group_dict["txKilobytesC"] = "group_count"

weewx.units.obs_group_dict["consoleRadioVersionC"] = "group_string"
weewx.units.obs_group_dict["consoleSwVersionC"] = "group_string"
weewx.units.obs_group_dict["consoleOsVersionC"] = "group_string"


weewx.units.obs_group_dict["sunshine_hours"] = "group_radiation"
weewx.units.obs_group_dict["sunshine_time"] = "group_radiation"

weewx.units.obs_group_dict["sunshineDur"] = "group_deltatime"
weewx.units.obs_group_dict["sunshineDur_2"] = "group_deltatime"
weewx.units.obs_group_dict["rainDur"] = "group_deltatime"
weewx.units.obs_group_dict["rainDur_2"] = "group_deltatime"

weewx.units.obs_group_dict["stormRain"] = "group_rain"
weewx.units.obs_group_dict["stormRainlast"] = "group_rain"
weewx.units.obs_group_dict["rain24"] = "group_rain"
weewx.units.obs_group_dict["rain60"] = "group_rain"
weewx.units.obs_group_dict["rain15"] = "group_rain"
weewx.units.obs_group_dict["hourRain"] = "group_rain"
weewx.units.obs_group_dict["totalRain"] = "group_rain"
weewx.units.obs_group_dict["dayET"] = "group_rain"
weewx.units.obs_group_dict["monthET"] = "group_rain"
weewx.units.obs_group_dict["yearET"] = "group_rain"
weewx.units.obs_group_dict["stormStart"] = "group_time"
weewx.units.obs_group_dict["windSpeed2"] = "group_speed2"

weewx.units.obs_group_dict["signal1"] = "group_percent"
weewx.units.obs_group_dict["signal2"] = "group_percent"
weewx.units.obs_group_dict["signal3"] = "group_percent"
weewx.units.obs_group_dict["signal4"] = "group_percent"
weewx.units.obs_group_dict["signal5"] = "group_percent"
weewx.units.obs_group_dict["signal6"] = "group_percent"
weewx.units.obs_group_dict["signal7"] = "group_percent"
weewx.units.obs_group_dict["signal8"] = "group_percent"
weewx.units.obs_group_dict["signal_2"] = "group_percent"
weewx.units.obs_group_dict["signala"] = "group_percent"
weewx.units.obs_group_dict["signalw"] = "group_percent"
weewx.units.obs_group_dict["signalr"] = "group_percent"

weewx.units.obs_group_dict["afc"] = "group_count"
weewx.units.obs_group_dict["txID"] = "group_count"
weewx.units.obs_group_dict["THW"] = "group_temperature"
weewx.units.obs_group_dict["outWetbulb"] = "group_temperature"
weewx.units.obs_group_dict["wetbulb1"] = "group_temperature"
weewx.units.obs_group_dict["windSpeed1"] = "group_speed2"
weewx.units.obs_group_dict["windDir1"] = "group_direction"
#weewx.units.obs_group_dict["windSpeed10"] = "group_speed2"
weewx.units.obs_group_dict["windDir10"] = "group_direction"
weewx.units.obs_group_dict["windGustSpeed10"] = "group_speed2"
weewx.units.obs_group_dict["windGustDir10"] = "group_direction"
#weewx.units.obs_group_dict["rainfall_last_60_min"] = "group_rain"
#weewx.units.obs_group_dict["rainfall_last_15_min"] = "group_rain"
weewx.units.obs_group_dict["dewpoint_1"] = "group_temperature"
weewx.units.obs_group_dict["dewpoint_2"] = "group_temperature"
weewx.units.obs_group_dict["dewpoint_3"] = "group_temperature"
weewx.units.obs_group_dict["dewpoint_4"] = "group_temperature"
weewx.units.obs_group_dict["wetbulb_1"] = "group_temperature"
weewx.units.obs_group_dict["wetbulb_2"] = "group_temperature"
weewx.units.obs_group_dict["wetbulb_3"] = "group_temperature"
weewx.units.obs_group_dict["wetbulb_4"] = "group_temperature"
weewx.units.obs_group_dict["heatindex_1"] = "group_temperature"
weewx.units.obs_group_dict["heatindex_2"] = "group_temperature"
weewx.units.obs_group_dict["heatindex_3"] = "group_temperature"
weewx.units.obs_group_dict["heatindex_4"] = "group_temperature"
weewx.units.obs_group_dict["rain_rate_hi_last_15_min"] = "group_rain"
#weewx.units.obs_group_dict["rainfall_last_24_hr"] = "group_rain"
weewx.units.obs_group_dict["rain_storm_start_at"] = "group_time"
weewx.units.obs_group_dict["rain_storm_last_start_at"] = "group_time"
weewx.units.obs_group_dict["rain_storm_last_end_at"] = "group_time"
weewx.units.obs_group_dict["txBatteryStatus"] = "group_count"
weewx.units.obs_group_dict["rssi"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent"] = "group_percent"
weewx.units.obs_group_dict["packets_received"] = "group_count"
weewx.units.obs_group_dict["packets_missed"] = "group_count"
weewx.units.obs_group_dict["crc_error"] = "group_count"
weewx.units.obs_group_dict["resyncs"] = "group_count"
weewx.units.obs_group_dict["supercapVolt"] = "group_volt"
weewx.units.obs_group_dict["solarVolt"] = "group_volt"
weewx.units.obs_group_dict["txBatteryVolt"] = "group_volt"

weewx.units.obs_group_dict["afc_2"] = "group_count"
weewx.units.obs_group_dict["txID_2"] = "group_count"
weewx.units.obs_group_dict["windSpeed_2"] = "group_speed2"
weewx.units.obs_group_dict["windDir_2"] = "group_direction"
weewx.units.obs_group_dict["windGust_2"] = "group_speed2"
weewx.units.obs_group_dict["windGustDir_2"] = "group_direction"
weewx.units.obs_group_dict["windSpeed1_2"] = "group_speed2"
weewx.units.obs_group_dict["windDir1_2"] = "group_direction"
weewx.units.obs_group_dict["windSpeed10_2"] = "group_speed2"
weewx.units.obs_group_dict["windDir10_2"] = "group_direction"
weewx.units.obs_group_dict["windGustSpeed10_2"] = "group_speed2"
weewx.units.obs_group_dict["windGustDir10_2"] = "group_direction"
weewx.units.obs_group_dict["outTemp_2"] = "group_temperature"
weewx.units.obs_group_dict["outHumidity_2"] =  "group_percent"
weewx.units.obs_group_dict["dewpoint2"] = "group_temperature"
weewx.units.obs_group_dict["heatindex2"] = "group_temperature"
weewx.units.obs_group_dict["windchill2"] = "group_temperature"
weewx.units.obs_group_dict["THSW_2"] = "group_temperature"
weewx.units.obs_group_dict["THW_2"] = "group_temperature"
weewx.units.obs_group_dict["outWetbulb_2"] = "group_temperature"
weewx.units.obs_group_dict["radiation_2"] = "group_radiation"
weewx.units.obs_group_dict["UV_2"] = "group_uv"
weewx.units.obs_group_dict["txBatteryStatus_2"] = "group_count"
#weewx.units.obs_group_dict["signal1_2"] = "group_count"
weewx.units.obs_group_dict["rain_2"] = "group_rain"
weewx.units.obs_group_dict["rainRate_2"] = "group_rainrate"
weewx.units.obs_group_dict["stormRain_2"] = "group_rain"
weewx.units.obs_group_dict["stormRainlast_2"] = "group_rain"
weewx.units.obs_group_dict["rain15_2"] = "group_rain"
weewx.units.obs_group_dict["rain60_2"] = "group_rain"
weewx.units.obs_group_dict["rain24_2"] = "group_rain"
weewx.units.obs_group_dict["dayRain_2"] = "group_rain"
weewx.units.obs_group_dict["monthRain_2"] = "group_rain"
weewx.units.obs_group_dict["yearRain_2"] = "group_rain"
weewx.units.obs_group_dict["rain_rate_hi_last_15_min_2"] = "group_rain"
weewx.units.obs_group_dict["rainfall_last_24_hr_2"] = "group_rain"
weewx.units.obs_group_dict["rain_storm_start_at_2"] = "group_time"
weewx.units.obs_group_dict["rain_storm_last_start_at_2"] = "group_time"
weewx.units.obs_group_dict["rain_storm_last_end_at_2"] = "group_time"
weewx.units.obs_group_dict["ET_2"] = "group_rain"
weewx.units.obs_group_dict["dayET_2"] = "group_rain"
weewx.units.obs_group_dict["monthET_2"] = "group_rain"
weewx.units.obs_group_dict["yearET_2"] = "group_rain"
weewx.units.obs_group_dict["rssi_2"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent_2"] = "group_percent"
weewx.units.obs_group_dict["packets_received_2"] = "group_count"
weewx.units.obs_group_dict["packets_missed_2"] = "group_count"
weewx.units.obs_group_dict["crc_error_2"] = "group_count"
weewx.units.obs_group_dict["resyncs_2"] = "group_count"
weewx.units.obs_group_dict["supercapVolt_2"] = "group_volt"
weewx.units.obs_group_dict["solarVolt_2"] = "group_volt"
weewx.units.obs_group_dict["txBatteryVolt_2"] = "group_volt"

weewx.units.obs_group_dict["windrun_2"] = "group_distance"

weewx.units.obs_group_dict["afc2"] = "group_count"
weewx.units.obs_group_dict["txID2"] = "group_count"
weewx.units.obs_group_dict["rssi2"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent2"] = "group_percent"
weewx.units.obs_group_dict["packets_received2"] = "group_count"
weewx.units.obs_group_dict["packets_missed2"] = "group_count"
weewx.units.obs_group_dict["crc_error2"] = "group_count"
weewx.units.obs_group_dict["resyncs2"] = "group_count"

weewx.units.obs_group_dict["afc3"] = "group_count"
weewx.units.obs_group_dict["txID3"] = "group_count"
weewx.units.obs_group_dict["rssi3"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent3"] = "group_percent"
weewx.units.obs_group_dict["packets_received3"] = "group_count"
weewx.units.obs_group_dict["packets_missed3"] = "group_count"
weewx.units.obs_group_dict["crc_error3"] = "group_count"
weewx.units.obs_group_dict["resyncs3"] = "group_count"

weewx.units.obs_group_dict["afc4"] = "group_count"
weewx.units.obs_group_dict["txID4"] = "group_count"
weewx.units.obs_group_dict["rssi4"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent4"] = "group_percent"
weewx.units.obs_group_dict["packets_received4"] = "group_count"
weewx.units.obs_group_dict["packets_missed4"] = "group_count"
weewx.units.obs_group_dict["crc_error4"] = "group_count"
weewx.units.obs_group_dict["resyncs4"] = "group_count"

weewx.units.obs_group_dict["afc5"] = "group_count"
weewx.units.obs_group_dict["txID5"] = "group_count"
weewx.units.obs_group_dict["rssi5"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent5"] = "group_percent"
weewx.units.obs_group_dict["packets_received5"] = "group_count"
weewx.units.obs_group_dict["packets_missed5"] = "group_count"
weewx.units.obs_group_dict["crc_error5"] = "group_count"
weewx.units.obs_group_dict["resyncs5"] = "group_count"

weewx.units.obs_group_dict["afc6"] = "group_count"
weewx.units.obs_group_dict["txID6"] = "group_count"
weewx.units.obs_group_dict["rssi6"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent6"] = "group_percent"
weewx.units.obs_group_dict["packets_received6"] = "group_count"
weewx.units.obs_group_dict["packets_missed6"] = "group_count"
weewx.units.obs_group_dict["crc_error6"] = "group_count"
weewx.units.obs_group_dict["resyncs6"] = "group_count"

weewx.units.obs_group_dict["afc7"] = "group_count"
weewx.units.obs_group_dict["txID7"] = "group_count"
weewx.units.obs_group_dict["rssi7"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent7"] = "group_percent"
weewx.units.obs_group_dict["packets_received7"] = "group_count"
weewx.units.obs_group_dict["packets_missed7"] = "group_count"
weewx.units.obs_group_dict["crc_error7"] = "group_count"
weewx.units.obs_group_dict["resyncs7"] = "group_count"

weewx.units.obs_group_dict["afc8"] = "group_count"
weewx.units.obs_group_dict["txID8"] = "group_count"
weewx.units.obs_group_dict["rssi8"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercent8"] = "group_percent"
weewx.units.obs_group_dict["packets_received8"] = "group_count"
weewx.units.obs_group_dict["packets_missed8"] = "group_count"
weewx.units.obs_group_dict["crc_error8"] = "group_count"
weewx.units.obs_group_dict["resyncs8"] = "group_count"

weewx.units.obs_group_dict["afcw"] = "group_count"
weewx.units.obs_group_dict["txIDw"] = "group_count"
weewx.units.obs_group_dict["rssiw"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercentw"] = "group_percent"
weewx.units.obs_group_dict["packets_receivedw"] = "group_count"
weewx.units.obs_group_dict["packets_missedw"] = "group_count"
weewx.units.obs_group_dict["crc_errorw"] = "group_count"
weewx.units.obs_group_dict["resyncsw"] = "group_count"

weewx.units.obs_group_dict["afcr"] = "group_count"
weewx.units.obs_group_dict["txIDr"] = "group_count"
weewx.units.obs_group_dict["rssir"] = "group_decibels"
weewx.units.obs_group_dict["rxCheckPercentr"] = "group_percent"
weewx.units.obs_group_dict["packets_receivedr"] = "group_count"
weewx.units.obs_group_dict["packets_missedr"] = "group_count"
weewx.units.obs_group_dict["crc_errorr"] = "group_count"
weewx.units.obs_group_dict["resyncsr"] = "group_count"

weewx.units.USUnits["group_hdd"] = "hdd"
weewx.units.MetricUnits["group_hdd"] = "hdd"
weewx.units.MetricWXUnits["group_hdd"] = "hdd"
weewx.units.default_unit_format_dict["hdd"] = "%.3f"
weewx.units.default_unit_label_dict["hdd"] = " "

#    "cooldeg"           : "group_degree_day",
#    "heatdeg"           : "group_degree_day",
#    "group_degree_day"  : "degree_F_day",
#    "group_degree_day"  : "degree_C_day",

weewx.units.obs_group_dict["cdd_day"] = "group_hdd" 	
weewx.units.obs_group_dict["hdd_day"] = "group_hdd"
weewx.units.obs_group_dict["cdd_day_2"] = "group_hdd"
weewx.units.obs_group_dict["hdd_day_2"] = "group_hdd"
weewx.units.obs_group_dict["cddc_day"] = "group_hdd"
weewx.units.obs_group_dict["hddc_day"] = "group_hdd"
weewx.units.obs_group_dict["cddc_day_2"] = "group_hdd"
weewx.units.obs_group_dict["hddc_day_2"] = "group_hdd"

#weewx.units.obs_group_dict['co2_Temp'] = 'group_temperature'
#weewx.units.obs_group_dict['dew_point'] = 'group_temperature'
#weewx.units.obs_group_dict['wet_bulb'] = 'group_temperature'
#weewx.units.obs_group_dict['heat_index'] = 'group_temperature'
#weewx.units.obs_group_dict['co2_Hum'] = 'group_percent'

weewx.units.obs_group_dict['pm10_0_nowcast'] = 'group_concentration'
weewx.units.obs_group_dict['pm2_5_nowcast'] = 'group_concentration'
weewx.units.obs_group_dict['pm_2p5_last_1_hour'] = 'group_concentration'
weewx.units.obs_group_dict['pm_2p5_last_3_hours'] = 'group_concentration'
weewx.units.obs_group_dict['pm_2p5_last_24_hours'] = 'group_concentration'
weewx.units.obs_group_dict['pm_10_last_1_hour'] = 'group_concentration'
weewx.units.obs_group_dict['pm_10_last_3_hours'] = 'group_concentration'
weewx.units.obs_group_dict['pm_10_last_24_hours'] = 'group_concentration'

weewx.units.default_unit_format_dict["microgram_per_meter_cubed"] = "%.1f"

weewx.units.obs_group_dict['pct_pm_data_nowcast'] = 'group_percent'
weewx.units.obs_group_dict['pct_pm_data_last_1_hour'] = 'group_percent'
weewx.units.obs_group_dict['pct_pm_data_last_3_hours'] = 'group_percent'
weewx.units.obs_group_dict['pct_pm_data_last_24_hours'] = 'group_percent'

weewx.units.obs_group_dict["rssiA"] = "group_decibels"
weewx.units.obs_group_dict["firmwareVersionA"] = "group_time"
#weewx.units.obs_group_dict["bootloaderVersionA"] = "group_count"
weewx.units.obs_group_dict["bootloaderVersionA"] = "group_time"
weewx.units.obs_group_dict["localAPIQueriesA"] = "group_count"
weewx.units.obs_group_dict["healthVersionA"] = "group_count"
weewx.units.obs_group_dict["uptimeA"] = "group_deltatime"
weewx.units.obs_group_dict["linkUptimeA"] = "group_deltatime"
weewx.units.obs_group_dict["rxPacketsA"] = "group_count"
weewx.units.obs_group_dict["txPacketsA"] = "group_count"
weewx.units.obs_group_dict["errorPacketsA"] = "group_count"
weewx.units.obs_group_dict["droppedPacketsA"] = "group_count"
weewx.units.obs_group_dict["recordWriteCountA"] = "group_count"
weewx.units.obs_group_dict["iFreeMemChunkA"] = "group_data"
weewx.units.obs_group_dict["iFreeMemWatermA"] = "group_data"
weewx.units.obs_group_dict["iUsedMemA"] = "group_data"
weewx.units.obs_group_dict["iFreeMemA"] = "group_data"
weewx.units.obs_group_dict["tUsedMemA"] = "group_data"
weewx.units.obs_group_dict["tFreeMemA"] = "group_data"


MM2INCH = 1 / 25.4

def loader(config_dict, engine):
    return DavisConsoleAPIDriver(**config_dict[DRIVER_NAME])


def get_historical_url(parameters, api_secret):
    """Construct a valid v2 historical API URL"""

    # Get historical API data
    # Now concatenate all parameters into a string
    urltext = ""
    for key in parameters:
        urltext = urltext + key + str(parameters[key])
    # Now calculate the API signature using the API secret
    api_signature = hmac.new(
        api_secret.encode("utf-8"), urltext.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    # Finally assemble the URL
    apiurl = (
        "https://api.weatherlink.com/v2/historic/%s?api-key=%s&start-timestamp=%s&end-timestamp=%s&api-signature=%s&t=%s"
        % (
            parameters["station-id"],
            parameters["api-key"],
            parameters["start-timestamp"],
            parameters["end-timestamp"],
            api_signature,
            parameters["t"],
        )
    )
    # loginf("apiurl %s" % apiurl)
    return apiurl


def get_current_url(parameters, api_secret):
    """Construct a valid v2 current API URL"""

    # Remove parameters the current API does not require
    parameters.pop("start-timestamp", None)
    parameters.pop("end-timestamp", None)
    urltext = ""
    for key in parameters:
        urltext = urltext + key + str(parameters[key])
    api_signature = hmac.new(
        api_secret.encode("utf-8"), urltext.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    apiurl = (
        "https://api.weatherlink.com/v2/current/%s?api-key=%s&api-signature=%s&t=%s"
        % (
            parameters["station-id"],
            parameters["api-key"],
            api_signature,
            parameters["t"],
        )
    )
    return apiurl

def get_json(url, uerror):
    """Retrieve JSON data from the API"""
    uerror = False
    timeout = 10

    try:
        response = requests.get(url, timeout=timeout)
    except requests.Timeout as error:
        logerr("Message: %s" % error)
        uerror = True
    except requests.RequestException as error:
        logerr("RequestException: %s" % error)
        uerror = True
    except:
        logerr("Error at get_json")
        uerror = True
    if not uerror:
     return response.json()
    else:
     return
   

def decode_historical_json(data, self):
    """Read the historical API JSON data"""

    found0 = False
    found1 = False
    found2 = False
    found3 = False
    found4 = False
    found5 = False
    found6 = False
    found7 = False

    iss_data = None
    iss2_data = None
    leaf_soil_data = None
    c_bar_data = None
    c_temp_hum_data = None
    extra_data1 = None
    extra_data2 = None
    extra_data3 = None
    extra_data4 = None
    leaf_data = None
    soil_data = None
    wind_data = None
    rain_data = None
    health_data = None
    max_count = 0

    h_packet = dict()

    try:
        historical_data = data["sensors"]
        if ((self.packet_log >= 0) or (self.max_count == 0)) and not self.found:
         try:  
          for i in range(13):
            tx_id = None
            if historical_data[i]["data"] and (
                historical_data[i]["data_structure_type"] == 20
                 or historical_data[i]["data_structure_type"] == 22
                 or historical_data[i]["data_structure_type"] == 24
                 or historical_data[i]["data_structure_type"] == 26
                 or historical_data[i]["data_structure_type"] == 27):
                values = historical_data[i]["data"][0]
                tx_id = values.get("tx_id")
                loginf("Found historical data from data ID %s Struc: %s Sensortype %s tx_id %s" % (i, historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"], tx_id) )
                #if historical_data[i]["data_structure_type"] == 26 and self.txid_leaf is None and self.txid_soil is None:
                #   self.txid_leaf_soil = True
            self.found = True
            max_count = i+1
         except IndexError as error:
            i == 13

        if self.max_count == 0 or max_count > self.max_count:
           self.max_count = max_count
 
        for i in range(self.max_count):
            if historical_data[i]["data"] and (
                historical_data[i]["data_structure_type"] == 20):
                logdbg("Found historical Barometer data")
                values = historical_data[i]["data"][0]

                if self.packet_log >= 2:
                  loginf("Use historical Barometer data - Struc: %s Sensortype %s" % (historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"]) )

                h_packet["pressure"] = values["bar_absolute"]
                h_packet["barometer"] = values["bar_sea_level"]
                break

        for i in range(self.max_count):
            if historical_data[i]["data"] and (
                historical_data[i]["data_structure_type"] == 22):
                logdbg("Found historical Internal Temperature data")
                values = historical_data[i]["data"][0]

                if self.packet_log >= 2:
                  loginf("Use historical Internal Temperature data - Struc: %s Sensortype %s" % (historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"]) )

                h_packet["inTemp"] = values["temp_in_last"]
                h_packet["inHumidity"] = values["hum_in_last"]
                h_packet["inDewpoint"] = values["dew_point_in_last"]
                break

        for i in range(self.max_count):
            if historical_data[i]["data"] and (
                historical_data[i]["data_structure_type"] == 27):
                logdbg("Found historical Health data")
                values = historical_data[i]["data"][0]

                if self.packet_log >= 2:
                  loginf("Use historical Health data - Struc: %s Sensortype %s" % (historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"]) )

                h_packet["consoleBatteryC"] = values["battery_voltage"]
                h_packet["rssiC"] = values["wifi_rssi"]
                h_packet["consoleApiLevelC"] = values["console_api_level"]
                h_packet["queueKilobytesC"] = values["queue_kilobytes"]
                h_packet["freeMemC"] = values["free_mem"]
                h_packet["systemFreeSpaceC"] = values["system_free_space"]
                h_packet["chargerPluggedC"] = values["charger_plugged"]
                h_packet["batteryPercentC"] = values["battery_percent"]
                h_packet["localAPIQueriesC"] = values["local_api_queries"]
                h_packet["healthVersionC"] = values["health_version"]
                h_packet["linkUptimeC"] = values["link_uptime"]
                h_packet["rxKilobytesC"] = values["rx_kilobytes"]
                h_packet["connectionUptimeC"] = values["connection_uptime"]
                h_packet["osUptimeC"] = values["os_uptime"]
                h_packet["batteryConditionC"] = values["battery_condition"]
                h_packet["iFreeSpaceC"] = values["internal_free_space"]
                h_packet["batteryCurrentC"] = values["battery_current"]
                h_packet["batteryStatusC"] = values["battery_status"]
                h_packet["databaseKilobytesC"] = values["database_kilobytes"]
                h_packet["batteryCycleCountC"] = values["battery_cycle_count"]
                h_packet["bootloaderVersionC"] = values["bootloader_version"]
                h_packet["clockSourceC"] = values["clock_source"]
                h_packet["appUptimeC"] = values["app_uptime"]
                h_packet["batteryTempC"] = values["battery_temp"]
                h_packet["txKilobytesC"] = values["tx_kilobytes"]
                h_packet["consoleRadioVersionC"] = values["console_radio_version"]
                h_packet["consoleSwVersionC"] = values["console_sw_version"]
                h_packet["consoleOsVersionC"] = values["console_os_version"]
                break

        for i in range(self.max_count):
            tx_id = None
            if historical_data[i]["data"] and (
                historical_data[i]["data_structure_type"] == 24):
                logdbg("Found historical data from data ID %s" % i)
                values = historical_data[i]["data"][0]

                tx_id = values.get("tx_id")
                if self.txid_iss == tx_id:
                  if self.packet_log >= 1:
                    loginf("Use historical data from data ID %s Struc: %s Sensortype %s tx_id %s" % (i, historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"], tx_id) )

                  h_packet["windSpeed"] = values["wind_speed_avg"]
                  h_packet["windDir"] = values["wind_dir_of_avg"]
                  h_packet["windGust"] = values["wind_speed_hi"]
                  h_packet["windGustDir"] = values["wind_speed_hi_dir"]

                  h_packet["outTemp"] = values["temp_avg"]
                  h_packet["outHumidity"] = values["hum_last"]
                  h_packet["dewpoint"] = values["dew_point_last"]
                  h_packet["heatindex"] = values["heat_index_last"]
                  h_packet["windchill"] = values["wind_chill_last"]
                  h_packet["THSW"] = values["thsw_index_last"]
                  h_packet["THW"] = values["thw_index_last"]
                  h_packet["outWetbulb"] = values["wet_bulb_last"]
                  h_packet["radiation"] = values["solar_rad_avg"]
                  h_packet["UV"] = values["uv_index_avg"]
                  h_packet["txBatteryStatus"] = values["trans_battery_flag"]
                  h_packet["batteryStatus"] = values["trans_battery_flag"]
                  h_packet["hdd"] = values["hdd"]
                  h_packet["cdd"] = values["cdd"]
                  h_packet["ET"] = values["et"]

                  #type = values["rain_size"]
                  h_packet["rainRate"] = values["rain_rate_hi_in"]
                  h_packet["rain"] = values["rainfall_in"]

                  h_packet["rssi"] = values["rssi"]
                  h_packet["reception"] = values["reception"]
                  h_packet["packets_received_current"] = values["packets_received"]
                  h_packet["crc_error_current"] = values["crc_errors"]
                  h_packet["supercapVolt"] = values["supercap_volt_last"]
                  h_packet["solarVolt"] = values["solar_volt_last"]
                  h_packet["txBatteryVolt"] = values["trans_battery_volt"]
                  h_packet["txID"] = values["tx_id"]

                  found0 = True
                  break


        if self.txid_iss2 is not None:
          for i in range(self.max_count):
            tx_id = None
            if historical_data[i]["data"] and (
                historical_data[i]["data_structure_type"] == 24):
               values = historical_data[i]["data"][0]

               tx_id = values.get("tx_id")
               if self.txid_iss2 == tx_id:
                  if self.packet_log >= 2:
                    loginf("Use historical data from data ID %s Struc: %s Sensortype %s tx_id %s" % (i, historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"], tx_id) )

                  h_packet["windSpeed_2"] = values["wind_speed_avg"]
                  h_packet["windDir_2"] = values["wind_dir_of_avg"]
                  h_packet["windGust_2"] = values["wind_speed_hi"]
                  h_packet["windGustDir_2"] = values["wind_speed_hi_dir"]

                  h_packet["outTemp_2"] = values["temp_avg"]
                  h_packet["outHumidity_2"] = values["hum_last"]
                  h_packet["dewpoint2"] = values["dew_point_last"]
                  h_packet["heatindex2"] = values["heat_index_last"]
                  h_packet["windchill2"] = values["wind_chill_last"]
                  h_packet["THSW_2"] = values["thsw_index_last"]
                  h_packet["THW_2"] = values["thw_index_last"]
                  h_packet["outWetbulb_2"] = values["wet_bulb_last"]
                  h_packet["radiation_2"] = values["solar_rad_avg"]
                  h_packet["UV_2"] = values["uv_index_avg"]
                  h_packet["txBatteryStatus_2"] = values["trans_battery_flag"]
                  h_packet["hdd_2"] = values["hdd"]
                  h_packet["cdd_2"] = values["cdd"]
                  h_packet["ET_2"] = values["et"]

                  #type = values["rain_size"]

                  h_packet["rainRate_2"] = values["rain_rate_hi_in"]
                  h_packet["rain_2"] = values["rainfall_in"]

                  h_packet["rssi_2"] = values["rssi"]
                  h_packet["reception_2"] = values["reception"]
                  h_packet["packets_received_current_2"] = values["packets_received"]
                  h_packet["crc_error_current_2"] = values["crc_errors"]
                  h_packet["supercapVolt_2"] = values["supercap_volt_last"]
                  h_packet["solarVolt_2"] = values["solar_volt_last"]
                  h_packet["txBatteryVolt_2"] = values["trans_battery_volt"]
                  h_packet["txID_2"] = values["tx_id"]

                  found1 = True
                  break

        if self.txid_leaf is not None:
          for i in range(self.max_count):
            tx_id = None
            if historical_data[i]["data"] and (
               historical_data[i]["data_structure_type"] == 26):
               values = historical_data[i]["data"][0]

               tx_id = values.get("tx_id")
               if self.txid_leaf == tx_id:
                  if self.packet_log >= 4:
                    loginf("Use historical Leaf data from data ID %s Struc: %s Sensortype %s tx_id %s" % (i, historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"], tx_id) )

                  h_packet["leafTemp1"] = values["temp_last_1"]
                  h_packet["leafTemp2"] = values["temp_last_2"]
                  h_packet["leafWet1"] = values["wet_leaf_last_1"]
                  h_packet["leafWet2"] = values["wet_leaf_last_2"]
                  h_packet["batteryStatus7"] = values["trans_battery_flag"]
                  h_packet["rssi7"] = values["rssi"]
                  h_packet["txID7"] = values["tx_id"]
                  h_packet["rxCheckPercent7"] = values["reception"]
                  h_packet["packets_received7"] = values["packets_received"]
                  h_packet["packets_missed7"] = values["packets_missed"]
                  h_packet["crc_error7"] = values["crc_errors"]
                  h_packet["resyncs7"] = values["resyncs"]
                  h_packet["afc7"] = values["freq_index"]

                  break

        if self.txid_soil is not None:
          for i in range(self.max_count):
            tx_id = None
            if historical_data[i]["data"] and (
               historical_data[i]["data_structure_type"] == 26):
               values = historical_data[i]["data"][0]

               tx_id = values.get("tx_id")
               if self.txid_soil == tx_id:
                  if self.packet_log >= 4:
                    loginf("Use historical Soil data from data ID %s Struc: %s Sensortype %s tx_id %s" % (i, historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"], tx_id) )

                  h_packet["leafTemp1"] = values["temp_last_1"]
                  h_packet["leafTemp2"] = values["temp_last_2"]
                  h_packet["leafTemp1"] = values["temp_last_3"]
                  h_packet["leafTemp2"] = values["temp_last_4"]
                  h_packet["soilMoist1"] = values["moist_soil_last_1"]
                  h_packet["soilMoist2"] = values["moist_soil_last_2"]
                  h_packet["soilMoist3"] = values["moist_soil_last_3"]
                  h_packet["soilMoist4"] = values["moist_soil_last_4"]
                  h_packet["leafWet1"] = values["wet_leaf_last_1"]
                  h_packet["leafWet2"] = values["wet_leaf_last_2"]
                  h_packet["batteryStatus6"] = values["trans_battery_flag"]
                  h_packet["rssi6"] = values["rssi"]
                  h_packet["txID6"] = values["tx_id"]
                  h_packet["rxCheckPercent6"] = values["reception"]
                  h_packet["packets_received6"] = values["packets_received"]
                  h_packet["packets_missed6"] = values["packets_missed"]
                  h_packet["crc_error6"] = values["crc_errors"]
                  h_packet["resyncs6"] = values["resyncs"]
                  h_packet["afc6"] = values["freq_index"]

                  break

        if self.txid_leaf_soil is not None:
          for i in range(self.max_count):
            tx_id = None
            if historical_data[i]["data"] and (
               historical_data[i]["data_structure_type"] == 26):
               values = historical_data[i]["data"][0]

               tx_id = values.get("tx_id")
               if self.txid_leaf_soil == tx_id:
                  if self.packet_log >= 4:
                    loginf("Use historical Leaf_Soil data from data ID %s Struc: %s Sensortype %s tx_id %s" % (i, historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"], tx_id) )

                  h_packet["leafTemp1"] = values["temp_last_1"]
                  h_packet["leafTemp2"] = values["temp_last_2"]
                  h_packet["leafTemp1"] = values["temp_last_3"]
                  h_packet["leafTemp2"] = values["temp_last_4"]
                  h_packet["soilMoist1"] = values["moist_soil_last_1"]
                  h_packet["soilMoist2"] = values["moist_soil_last_2"]
                  h_packet["soilMoist3"] = values["moist_soil_last_3"]
                  h_packet["soilMoist4"] = values["moist_soil_last_4"]
                  h_packet["batteryStatus8"] = values["trans_battery_flag"]
                  h_packet["rssi8"] = values["rssi"]
                  h_packet["txID8"] = values["tx_id"]
                  h_packet["rxCheckPercent8"] = values["reception"]
                  h_packet["packets_received8"] = values["packets_received"]
                  h_packet["packets_missed8"] = values["packets_missed"]
                  h_packet["crc_error8"] = values["crc_errors"]
                  h_packet["resyncs8"] = values["resyncs"]
                  h_packet["afc8"] = values["freq_index"]

                  break

        if self.txid_wind is not None:
          for i in range(self.max_count):
            tx_id = None
            if historical_data[i]["data"] and (
               historical_data[i]["data_structure_type"] == 24
                 and historical_data[i]["sensor_type"] == 55):
               values = historical_data[i]["data"][0]

               tx_id = values.get("tx_id")
               if self.txid_wind == tx_id:
                  if self.packet_log >= 6:
                    loginf("Use historical Wind data from data ID %s Struc: %s Sensortype %s tx_id %s" % (i, historical_data[i]["data_structure_type"], historical_data[i]["sensor_type"], tx_id) )

                  h_packet["windSpeed"] = values["wind_speed_avg"]
                  h_packet["windDir"] = values["wind_dir_of_avg"]
                  h_packet["windGust"] = values["wind_speed_hi"]
                  h_packet["windGustDir"] = values["wind_speed_hi_dir"]

                  h_packet["windBatteryStatus"] = values["trans_battery_flag"]
                  h_packet["rssiw"] = values["rssi"]
                  h_packet["txIDw"] = values["tx_id"]
                  h_packet["rxCheckPercentw"] = values["reception"]
                  h_packet["packets_receivedw"] = values["packets_received"]
                  h_packet["packets_missedw"] = values["packets_missed"]
                  h_packet["crc_errorw"] = values["crc_errors"]
                  h_packet["resyncsw"] = values["resyncs"]
                  h_packet["afcw"] = values["freq_index"]

                  break


    except KeyError as error:
        logerr(
            "No valid historical  API data recieved. Double-check API "
            "key/secret and station id. Error is: %s" % error
        )
        logerr("The API data returned was: %s" % data)
    except IndexError as error:
        logerr(
            "No valid historical data structure types found in API data. "
            "Error is: %s" % error
        )
        logerr("The API data returned was: %s" % data)
    except:
        logerr("No historical data.")
  
    return h_packet


def decode_current_json(data, self):
    """Read the current API JSON data"""

    iss_data = None
    iss2_data = None
    leaf_soil_data = None
    c_bar_data = None
    c_temp_hum_data = None
    extra_data1 = None
    extra_data2 = None
    extra_data3 = None
    extra_data4 = None
    leaf_data = None
    soil_data = None
    wind_data = None
    rain_data = None
    health_data = None
    airlink_data = None
    airlinkhealth_data = None

    c_packet = dict() 

    self.current_davis_data = data
    try:
     for sensor in data['sensors']:
        # 19 = Console BAR Current sensors record
        # 21 = Console Temp/Hum Current sensors record
        # 23 = ISS Current sensors record
        # 25 = Leaf/Soil Moisture Current sensors record
        # 27 = Health record
        
        if sensor.get('data_structure_type') == 23:
          self.ts = sensor["data"][0]["ts"]
          id = sensor["data"][0]["tx_id"]
          if id == self.txid_iss:
              iss_data = sensor
              if sensor.get('sensor_type') == 43:
                 isstxt = 'ISS'
              else:
                 isstxt = 'VUE'                 
              #loginf("iss_txid: %s" % sensor["data"][0]["tx_id"])
              logdbg("Found current data from data ID %s" % sensor["data"][0]["tx_id"])
              if self.iss_found == False:
                loginf("Found current %s data from data ID %s" % (isstxt, sensor["data"][0]["tx_id"]))
                self.iss_found = True

        if sensor.get('data_structure_type') == 25:
          id = sensor["data"][0]["tx_id"]
          if id == self.txid_soil:
              soil_data = sensor
              #loginf("soil_txid: %s" % sensor["data"][0]["tx_id"])
              logdbg("Found current soil data from data ID %s" % sensor["data"][0]["tx_id"])
              if self.soil_found == False:
                loginf("Found current Soil data from data ID %s" % sensor["data"][0]["tx_id"])
                self.soil_found = True
          if id == self.txid_leaf:
              leaf_data = sensor
              #loginf("leaf_txid: %s" % sensor["data"][0]["tx_id"])
              logdbg("Found current Leaf data from data ID %s" % sensor["data"][0]["tx_id"])
              if self.leaf_found == False:
                loginf("Found current Leaf data from data ID %s" % sensor["data"][0]["tx_id"])
                self.leaf_found = True
          if id == self.txid_leaf_soil:
              leaf_soil_data = sensor
              #loginf("leaf_soil_txid: %s" % sensor["data"][0]["tx_id"])
              logdbg("Found current Leaf/Soil data from data ID %s" % sensor["data"][0]["tx_id"])
              if self.leaf_soil_found == False:
                loginf("Found current Leaf/Soil data from data ID %s" % sensor["data"][0]["tx_id"])
                self.leaf_soil_found = True

        if sensor.get('data_structure_type') == 19:
         c_bar_data = sensor

        if sensor.get('data_structure_type') == 21:
         c_temp_hum_data = sensor

        if sensor.get('data_structure_type') == 23 and sensor.get('sensor_type') == 55:
          id = sensor["data"][0]["tx_id"]
          if self.extra1_found == False and self.extra2_found == False and self.extra2_found == False and self.extra4_found == False:
            loginf("Found data from sensor_type 55 and data ID %s" % id)
          if id == self.txid_wind:
             test = sensor["data"][0]["wind_speed_avg_last_10_min"]
             if test is not None:
                wind_data = sensor             
                logdbg("Found current Wind data from data ID %s" % sensor["data"][0]["tx_id"])
                if self.wind_found == False:
                   loginf("Found current Wind data from data ID %s" % sensor["data"][0]["tx_id"])
                   self.wind_found = True

          if id == self.txid_rain:
             test = sensor["data"][0]["rainfall_last_15_min"]
             if test is not None:
                rain_data = sensor             
                logdbg("Found current Rain data from data ID %s" % sensor["data"][0]["tx_id"])
                if self.rain_found == False:
                   loginf("Found current Rain data from data ID %s" % sensor["data"][0]["tx_id"])
                   self.rain_found = True

          if id == self.txid_extra1:
             test = sensor["data"][0]["temp"]
             test1 = sensor["data"][0]["rssi_last"]
             #loginf("extra1 rssi: %s" % test1)
             if test is not None or test1 is not None:
                extra1_data = sensor
                if test is None:
                  logdbg("Found none Temp data from data ID %s" % sensor["data"][0]["tx_id"])
                else: 
                  logdbg("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                if self.extra1_found == False:
                   if test is None: 
                     loginf("Found none Temp data from data ID %s" % sensor["data"][0]["tx_id"])
                   else:
                     loginf("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                   self.extra1_found = True

          if id == self.txid_extra2:
             test = sensor["data"][0]["temp"]
             test1 = sensor["data"][0]["rssi_last"]
             if test is not None or test1 is not None:
                extra2_data = sensor             
                if test is None:
                  logdbg("Found none Temp data from data ID %s" % sensor["data"][0]["tx_id"])
                else: 
                  logdbg("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                if self.extra2_found == False:
                   if test is None: 
                     loginf("Found none Temp data from data ID %s" % sensor["data"][0]["tx_id"])
                   else:
                     loginf("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                   self.extra2_found = True

          if id == self.txid_extra3:
             test = sensor["data"][0]["temp"]
             if test is not None:
                extra3_data = sensor             
                logdbg("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                if self.extra3_found == False:
                   loginf("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                   self.extra3_found = True

          if id == self.txid_extra4:
             test = sensor["data"][0]["temp"]
             if test is not None:
                extra4_data = sensor             
                logdbg("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                if self.extra4_found == False:
                   loginf("Found current Temp/Hum data from data ID %s" % sensor["data"][0]["tx_id"])
                   self.extra4_found = True

        if sensor.get('data_structure_type') == 23:
          id = sensor["data"][0]["tx_id"]
          if id == self.txid_iss2:
              iss2_data = sensor
              if sensor.get('sensor_type') == 43:
                 isstxt = 'ISS'
              else:
                 isstxt = 'VUE'                 
              #loginf("iss2_txid: %s" % sensor["data"][0]["tx_id"])
              logdbg("Found current ISS/VUE data from data ID %s" % sensor["data"][0]["tx_id"])
              if self.iss2_found == False:
                loginf("Found current %s data from data ID %s" % (isstxt, sensor["data"][0]["tx_id"]))
                self.iss2_found = True

        if sensor.get('data_structure_type') == 27:
         self.tshealth = sensor["data"][0]["ts"]
         health_data = sensor

        if sensor.get('data_structure_type') == 16:
           airlink_data = sensor
           logdbg("Found current Airlink data")
           if self.airlink_found == False:
                   loginf("Found current Airlink data")
                   self.airlink_found = True

        if sensor.get('data_structure_type') == 18:
           airlinkhealth_data = sensor
           logdbg("Found current Airlink Health data")
           if self.airlinkhealth_found == False:
                   loginf("Found current Airlink Health data")
                   self.airlinkhealth_found = True


    except:   
       loginf("No Sensor data found")
       return c_packet


    if iss_data:
      if self.packet_log == 3:
           loginf("iss_data: %s" % iss_data)
      values = iss_data["data"][0]
      #loginf("iss values: %s" % values)
      #loginf("iss temp: %s" % values["temp"])
      if values["temp"]:
        c_packet["windSpeed"] = values["wind_speed_last"]
        c_packet["windDir"] = values["wind_dir_last"]
        c_packet["windGust"] = values["wind_speed_hi_last_2_min"]
        c_packet["windGustDir"] = values["wind_dir_at_hi_speed_last_2_min"]

        c_packet["windSpeed1"] = values["wind_speed_avg_last_1_min"]
        c_packet["windDir1"] = values["wind_dir_scalar_avg_last_1_min"]
        c_packet["windSpeed10"] = values["wind_speed_avg_last_10_min"]
        c_packet["windDir10"] = values["wind_dir_scalar_avg_last_10_min"]
        c_packet["windGustSpeed10"] = values["wind_speed_hi_last_10_min"]
        c_packet["windGustDir10"] = values["wind_dir_at_hi_speed_last_10_min"]

        c_packet["outTemp"] = values["temp"]
        c_packet["outHumidity"] = values["hum"]
        c_packet["dewpoint"] = values["dew_point"]
        c_packet["heatindex"] = values["heat_index"]
        c_packet["windchill"] = values["wind_chill"]
        c_packet["THSW"] = values["thsw_index"]
        c_packet["THW"] = values["thw_index"]
        c_packet["outWetbulb"] = values["wet_bulb"]
        c_packet["radiation"] = values["solar_rad"]
        c_packet["UV"] = values["uv_index"]
        c_packet["txBatteryStatus"] = values["trans_battery_flag"]
        c_packet["batteryStatus"] = values["trans_battery_flag"]
        c_packet["signal1"] = values["rx_state"]
        c_packet["hdd_day"] = values["hdd_day"]
        if c_packet["hdd_day"] > 0:
           c_packet["hddc_day"] = 18 - ( (65 - c_packet["hdd_day"] - 32) * 5 / 9) 
        else:
           c_packet["hddc_day"] = 0

        c_packet["cdd_day"] = values["cdd_day"]
        if c_packet["cdd_day"] > 0:
           c_packet["cddc_day"] = 18 + ( (65 + c_packet["cdd_day"] - 32) * 5 / 9) 
        else:
           c_packet["cddc_day"] = 0

        test = values["rainfall_day_in"]
        if test is not None:
          #loginf("test None")
          if self.raininit is False:
            #loginf("raininit False")
            # Check current rain for the day and set it
            self.rain_previous_period = test

            # Set date for previous rain
            self.rain_previous_date = datetime.datetime.fromtimestamp(self.raindatetime)
            #self.rain_previous_date = self.raindatetime

            self.raininit = True

          if self.raininit == True:
            #loginf("raininit True")
            c_packet["stormRain"] = values["rain_storm_current_in"]
            c_packet["stormRainlast"] = values["rain_storm_last_in"]
            c_packet["rain15"] = values["rainfall_last_15_min_in"]
            c_packet["rain60"] = values["rainfall_last_60_min_in"]
            c_packet["rain24"] = values["rainfall_last_24_hr_in"]
            c_packet["rain_rate_hi_last_15_min"] = values["rain_rate_hi_last_15_min_in"]
            c_packet["rain_storm_start_at"] = values["rain_storm_current_start_at"]
            c_packet["rain_storm_last_start_at"] = values["rain_storm_last_start_at"]
            c_packet["rain_storm_last_end_at"] = values["rain_storm_last_end_at"]
            c_packet["dayRain"] = test
            c_packet["monthRain"] = values["rainfall_month_in"]
            c_packet["yearRain"] = values["rainfall_year_in"]
            c_packet["rainRate"] = values["rain_rate_last_in"]

            rain_now = test - self.rain_previous_period
            rain_v = rain_now
            # self.rain_previous_period = 1 test = 0.2 -> rain_v = -0.8
            #c_packet["rain"] = 0
            if rain_v >= 0:
              c_packet["rain"] = rain_v
              if (self.packet_log == -1) and rain_v > 0:
                 loginf("rain %.2f mm " % (c_packet["rain"]*25.4))
            else: 
              if (rain_v-test < 0) and  (abs(rain_v) != test):			# -0.8 - 0.2 <0 (=-0.6) and 0.8<>0.2 = 0.6
                 c_packet["rain"] = test
                 if (self.packet_log == -1) and (c_packet["rain"] > 0): 
                    loginf("rainabs  %.2f mm" % (c_packet["rain"]*25.4))
              else:
                 c_packet["rain"] = 0
            self.rain_previous_period = test
            self.rain_previous_date = datetime.datetime.fromtimestamp(self.raindatetime)


        c_packet["dayET"] = values["et_day"]
        if values["et_day"] is not None:
           ET_now = values["et_day"] - self.ET_previous_period
           ET_v = ET_now
           if ET_v >= 0:
              c_packet["ET"] = ET_v
           else:
              c_packet["ET"] = 0
            
           self.ET_previous_period = values["et_day"]
        else:
           c_packet["ET"] = 0

        c_packet["monthET"] = values["et_month"]
        c_packet["yearET"] = values["et_year"]

        c_packet["rssi"] = values["rssi_last"]
        c_packet["rxCheckPercent"] = values["reception_day"]
        #c_packet["reception"] = values["reception_day"]
        c_packet["packets_received"] = values["packets_received_day"]
        c_packet["packets_missed"] = values["packets_missed_day"]
        c_packet["crc_error"] = values["crc_errors_day"]
        c_packet["resyncs"] = values["resyncs_day"]
        c_packet["supercapVolt"] = values["supercap_volt"]
        c_packet["solarVolt"] = values["solar_panel_volt"]
        c_packet["txBatteryVolt"] = values["trans_battery_volt"]
        c_packet["txID"] = values["tx_id"]
        c_packet["afc"] = values["freq_index"]

    if c_bar_data:
        if self.packet_log == 2:
           loginf("c_bar_data: %s" % c_bar_data)
        values = c_bar_data["data"][0]
        #c_packet["altimeter"] = values["bar_sea_level"]
        #if c_bar_data.get("bar_absolute"):
        c_packet["pressure"] = values["bar_absolute"]
        #if c_bar_data.get("bar_sea_level"):
        c_packet["barometer"] = values["bar_sea_level"]
        #loginf("barometer: %s" % c_packet["barometer"])

    if c_temp_hum_data:
        if self.packet_log == 2:
           loginf("c_temp_hum_data: %s" % c_temp_hum_data)
        values = c_temp_hum_data["data"][0]
        #loginf("temp_in: %s" % values["temp_in"])

        c_packet["inTemp"] = values["temp_in"]
        c_packet["inHumidity"] = values["hum_in"]
        c_packet["inDewpoint"] = values["dew_point_in"]
        #loginf("inTemp: %s" % c_packet["inTemp"])

    if leaf_data:
        if self.packet_log == 4:
           loginf("leaf_data: %s" % leaf_data)

        values = leaf_data["data"][0]

        c_packet["leafTemp1"] = values["temp_1"]
        c_packet["leafTemp2"] = values["temp_2"]
        c_packet["leafWet1"] = values["wet_leaf_1"]
        c_packet["leafWet2"] = values["wet_leaf_2"]
        c_packet["signal7"] = values["rx_state"]
        c_packet["batteryStatus7"] = values["trans_battery_flag"]
        c_packet["rssi7"] = values["rssi_last"]
        c_packet["txID7"] = values["tx_id"]
        c_packet["rxCheckPercent7"] = values["reception_day"]
        c_packet["packets_received7"] = values["packets_received_day"]
        c_packet["packets_missed7"] = values["packets_missed_day"]
        c_packet["crc_error7"] = values["crc_errors_day"]
        c_packet["resyncs7"] = values["resyncs_day"]
        c_packet["afc7"] = values["freq_index"]

    if soil_data:
        if self.packet_log == 4:
           loginf("soil_data: %s" % soil_data)

        values = soil_data["data"][0]

        c_packet["soilTemp1"] = values["temp_1"]
        c_packet["soilTemp2"] = values["temp_2"]
        c_packet["soilTemp3"] = values["temp_3"]
        c_packet["soilTemp4"] = values["temp_4"]
        c_packet["soilMoist1"] = values["moist_soil_1"]
        c_packet["soilMoist2"] = values["moist_soil_2"]
        c_packet["soilMoist3"] = values["moist_soil_3"]
        c_packet["soilMoist4"] = values["moist_soil_4"]
        c_packet["signal8"] = values["rx_state"]
        c_packet["batteryStatus8"] = values["trans_battery_flag"]
        c_packet["rssi8"] = values["rssi_last"]
        c_packet["txID8"] = values["tx_id"]
        c_packet["rxCheckPercent8"] = values["reception_day"]
        c_packet["packets_received8"] = values["packets_received_day"]
        c_packet["packets_missed8"] = values["packets_missed_day"]
        c_packet["crc_error8"] = values["crc_errors_day"]
        c_packet["resyncs8"] = values["resyncs_day"]
        c_packet["afc8"] = values["freq_index"]

    if leaf_soil_data:
        if self.packet_log == 4:
           loginf("leaf_soil_data: %s" % leaf_soil_data)

        values = leaf_soil_data["data"][0]

        c_packet["soilTemp1"] = values["temp_1"]
        c_packet["soilTemp2"] = values["temp_2"]
        c_packet["soilTemp3"] = values["temp_3"]
        c_packet["soilTemp4"] = values["temp_4"]
        c_packet["soilMoist1"] = values["moist_soil_1"]
        c_packet["soilMoist2"] = values["moist_soil_2"]
        c_packet["soilMoist3"] = values["moist_soil_3"]
        c_packet["soilMoist4"] = values["moist_soil_4"]
        c_packet["leafWet1"] = values["wet_leaf_1"]
        c_packet["leafWet2"] = values["wet_leaf_2"]
        c_packet["signal6"] = values["rx_state"]
        c_packet["batteryStatus6"] = values["trans_battery_flag"]
        c_packet["rssi6"] = values["rssi_last"]
        c_packet["txID6"] = values["tx_id"]
        c_packet["rxCheckPercent6"] = values["reception_day"]
        c_packet["packets_received6"] = values["packets_received_day"]
        c_packet["packets_missed6"] = values["packets_missed_day"]
        c_packet["crc_error6"] = values["crc_errors_day"]
        c_packet["resyncs6"] = values["resyncs_day"]
        c_packet["afc6"] = values["freq_index"]

    if extra_data1:
        if self.packet_log == 5:
           loginf("extra_data1: %s" % extra_data1)
        values = extra_data1["data"][0]

        c_packet["extraTemp1"] = values["temp"]
        c_packet["extraHumid1"] = values["hum"]
        c_packet["dewpoint_1"] = values["dew_point"]
        c_packet["wetbulb_1"] = values["wet_bulb"]
        c_packet["heatindex_1"] = values["heat_index"]

        test = ''
        #if extra_data1.get("rx_state") :
        c_packet["signal2"] = values["rx_state"]
        #else:
        #   test = extra_data1.get("rx_state", None) 
        #   if test != None:
        #     c_packet["signal2"] = test
 
        test = ''
        c_packet["batteryStatus2"] = values["trans_battery_flag"]
        #else:
        #   test = extra_data1.get("trans_battery_flag", None) 
        #   if test != None:
        #     c_packet["batteryStatus2"] = test
        #loginf("batteryStatus2: %s" % test)
        c_packet["rssi2"] = values["rssi_last"]
        c_packet["txID2"] = values["tx_id"]
        c_packet["rxCheckPercent2"] = values["reception_day"]
        c_packet["packets_received2"] = values["packets_received_day"]
        c_packet["packets_missed2"] = values["packets_missed_day"]
        c_packet["crc_error2"] = values["crc_errors_day"]
        c_packet["resyncs2"] = values["resyncs_day"]
        c_packet["afc2"] = values["freq_index"]

    if extra_data2:
        if self.packet_log == 5:
           loginf("extra_data2: %s" % extra_data2)
        values = extra_data2["data"][0]

        c_packet["extraTemp2"] = values["temp"]
        c_packet["extraHumid2"] = values["hum"]
        c_packet["dewpoint_2"] = values["dew_point"]
        c_packet["wetbulb_2"] = values["wet_bulb"]
        c_packet["heatindex_2"] = values["heat_index"]

        test = ''        
        #if extra_data2.get("rx_state"):
        c_packet["signal3"] = values["rx_state"]
        #else:
        #   test = extra_data2.get("rx_state", None) 
        #   if test != None:
        #     c_packet["signal3"] = test

        test = '' 
        c_packet["batteryStatus3"] = values["trans_battery_flag"]
        #else:
        #   test = extra_data2.get("trans_battery_flag", None) 
        #   if test != None:
        #     c_packet["batteryStatus3"] = test
        c_packet["rssi3"] = values["rssi_last"]
        c_packet["txID3"] = values["tx_id"]
        c_packet["rxCheckPercent3"] = values["reception_day"]
        c_packet["packets_received3"] = values["packets_received_day"]
        c_packet["packets_missed3"] = values["packets_missed_day"]
        c_packet["crc_error3"] = values["crc_errors_day"]
        c_packet["resyncs3"] = values["resyncs_day"]
        c_packet["afc3"] = values["freq_index"]

    if extra_data3:
        if self.packet_log == 5:
           loginf("extra_data3: %s" % extra_data3)
        values = extra_data3["data"][0]

        if values.get("temp"):
           c_packet["extraTemp3"] = values["temp"]
        if values.get("hum"):
           c_packet["extraHumid3"] = values["hum"]
        if values.get("dew_point"):
           c_packet["dewpoint_3"] = values["dew_point"]
        if values.get("wet_bulb"):
           c_packet["wetbulb_3"] = values["wet_bulb"]
        if values.get("heat_index"):
           c_packet["heatindex_3"] = values["heat_index"]

        test = ''  
        if values.get("rx_state"):
           c_packet["signal4"] = values["rx_state"]
        else:
           test = values.get("rx_state", None) 
           if test != None:
             c_packet["signal4"] = test

        test = ''  
        if values.get("trans_battery_flag"):
          c_packet["batteryStatus4"] = values["trans_battery_flag"]
        else:
           test = values.get("trans_battery_flag", None) 
           if test != None:
             c_packet["batteryStatus4"] = test
        c_packet["rssi4"] = values["rssi_last"]
        c_packet["txID4"] = values["tx_id"]
        c_packet["rxCheckPercent4"] = values["reception_day"]
        c_packet["packets_received4"] = values["packets_received_day"]
        c_packet["packets_missed4"] = values["packets_missed_day"]
        c_packet["crc_error4"] = values["crc_errors_day"]
        c_packet["resyncs4"] = values["resyncs_day"]
        c_packet["afc4"] = values["freq_index"]

    if extra_data4:
        if self.packet_log == 5:
           loginf("extra_data4: %s" % extra_data4)
        values = extra_data4["data"][0]

        if values.get("temp"):
           c_packet["extraTemp4"] = values["temp"]
        if values.get("hum"):
           c_packet["extraHumid4"] = values["hum"]
        if values.get("dew_point"):
           c_packet["dewpoint_4"] = values["dew_point"]
        if values.get("wet_bulb"):
           c_packet["wetbulb_4"] = values["wet_bulb"]
        if values.get("heat_index"):
           c_packet["heatindex_4"] = values["heat_index"]

        test = ''  
        if values.get("rx_state"):
           c_packet["signal5"] = values["rx_state"]
        else:
           test = values.get("rx_state", None) 
           if test != None:
             c_packet["signal5"] = test

        test = ''  
        if values.get("trans_battery_flag"):
         c_packet["batteryStatus5"] = values["trans_battery_flag"]
        else:
           test = values.get("trans_battery_flag", None) 
           if test != None:
             c_packet["batteryStatus5"] = test
        c_packet["rssi5"] = values["rssi_last"]
        c_packet["txID5"] = values["tx_id"]
        c_packet["rxCheckPercent5"] = values["reception_day"]
        c_packet["packets_received5"] = values["packets_received_day"]
        c_packet["packets_missed5"] = values["packets_missed_day"]
        c_packet["crc_error5"] = values["crc_errors_day"]
        c_packet["resyncs5"] = values["resyncs_day"]
        c_packet["afc5"] = values["freq_index"]

    if wind_data:
      if self.packet_log == 6:
           loginf("wind_data: %s" % wind_data)
      try:
        values = wind_data["data"][0]
      
        if values.get("wind_speed_last"):
          c_packet["windSpeed"] = values["wind_speed_last"]
        if values.get("wind_dir_last"):
          c_packet["windDir"] = values["wind_dir_last"]
        if values.get("wind_speed_hi_last_2_min"):
          c_packet["windGust"] = values["wind_speed_hi_last_2_min"]
        if values.get("wind_dir_at_hi_speed_last_2_min"):
          c_packet["windGustDir"] = values["wind_dir_at_hi_speed_last_2_min"]
        if values.get("wind_speed_avg_last_1_min"):
          c_packet["windSpeed1"] = values["wind_speed_avg_last_1_min"]
        if values.get("wind_dir_scalar_avg_last_1_min"):
          c_packet["windDir1"] = values["wind_dir_scalar_avg_last_1_min"]
        if values.get("wind_speed_avg_last_10_min"):
          c_packet["windSpeed10"] = values["wind_speed_avg_last_10_min"]
        if values.get("wind_dir_scalar_avg_last_10_min"):
          c_packet["windDir10"] = values["wind_dir_scalar_avg_last_10_min"]
        if values.get("wind_speed_hi_last_10_min"):
          c_packet["windGustSpeed10"] = values["wind_speed_hi_last_10_min"]
        if values.get("wind_dir_at_hi_speed_last_10_min"):
          c_packet["windGustDir10"] = values["wind_dir_at_hi_speed_last_10_min"]

        test = ''
        if values.get("rx_state"):
           c_packet["signalw"] = values["rx_state"]
        else:
           test = values.get("rx_state", None) 
           if test != None:
             c_packet["signalw"] = test

        test = ''  
        if values.get("trans_battery_flag"):
          c_packet["windBatteryStatus"] = values["trans_battery_flag"]
        else:
           test = values.get("trans_battery_flag", None) 
           if test != None:
             c_packet["windBatteryStatus"] = test
        c_packet["rssiw"] = values["rssi_last"]
        c_packet["txIDw"] = values["tx_id"]
        c_packet["rxCheckPercentw"] = values["reception_day"]
        c_packet["packets_receivedw"] = values["packets_received_day"]
        c_packet["packets_missedw"] = values["packets_missed_day"]
        c_packet["crc_errorw"] = values["crc_errors_day"]
        c_packet["resyncsw"] = values["resyncs_day"]
        c_packet["afcw"] = values["freq_index"]

        #packet["windBatteryStatus"] = values["trans_battery_flag"]
        #if values.get("rx_state"):
        #   c_packet["signalw"] = values["rx_state"]
      except:
        logerr("Problem with Wind data.")
     

    if rain_data:
      if self.packet_log == 6:
           loginf("rain_data: %s" % rain_data)
      try:
        values = rain_data["data"][0]

        test = values["rainfall_day_in"]
        if values["rainfall_day_in"]:
          if self.raininit is False:

              # Check current rain for the day and set it
              self.rain_previous_period = values["rainfall_day_in"]

              # Set date for previous rain
              self.rain_previous_date = datetime.datetime.fromtimestamp(self.raindatetime)
              self.raininit = True

          if self.raininit is True:
            if values["rain_storm_current_in"] != None:
               c_packet["stormRain"] = values["rain_storm_current_in"]
            if values["rain_storm_last_in"] != None:
               c_packet["stormRainlast"] = values["rain_storm_last_in"]
            if values["rainfall_last_15_min_in"] != None:
               c_packet["rain15"] = values["rainfall_last_15_min_in"]
            if values["rainfall_last_60_min_in"] != None:
               c_packet["rain60"] = values["rainfall_last_60_min_in"]
            if values["rainfall_last_24_hr_in"] != None:
               c_packet["rain24"] = values["rainfall_last_24_hr_in"]
            if values["rain_rate_hi_last_15_min_in"] != None:
               c_packet["rain_rate_hi_last_15_min"] = values["rain_rate_hi_last_15_min_in"]

            c_packet["rain_storm_start_at"] = values["rain_storm_current_start_at"]
            if values["rain_storm_last_start_at"] != None:
               c_packet["rain_storm_last_start_at"] = values["rain_storm_last_start_at"]
            if values["rain_storm_last_end_at"] != None:
               c_packet["rain_storm_last_end_at"] = values["rain_storm_last_end_at"]

            c_packet["dayRain"] = values["rainfall_day_in"]
            if values["rainfall_month_in"] != None:
               c_packet["monthRain"] = values["rainfall_month_in"]
            if values["rainfall_year_in"] != None:
               c_packet["yearRain"] = values["rainfall_year_in"]
            if values["rain_rate_last_in"] != None:
               c_packet["rainRate"] = values["rain_rate_last_in"]

            #self.calculate_rain()

            rain_now = values["rainfall_day_in"] - self.rain_previous_period
            #rain_now = test - self.rain_previous_period

            rain_v = rain_now

            if rain_v >= 0:
              c_packet["rain"] = rain_v
              if (self.packet_log == 1) and rain_v > 0:
                 loginf("rain %.2f mm " % (c_packet["rain"]*25.4))
            else: 
              if (rain_v-test < 0) and  (abs(rain_v) != test):
                 c_packet["rain"] = test
                 if (self.packet_log == 1) and (c_packet["rain"] > 0): 
                    loginf("rainabs  %.2f mm" % (c_packet["rain"]*25.4))
              else:
                 c_packet["rain"] = 0

            rain_v = rain_now

            self.rain_previous_period = values["rainfall_day_in"]
            self.rain_previous_date = datetime.datetime.fromtimestamp(self.raindatetime)


        test = ''  
        if values.get("rx_state"):
           c_packet["signalr"] = values["rx_state"]
        else:
           test = values.get("rx_state", None) 
           if test != None:
             c_packet["signalr"] = test

        test = ''  
        if values.get("trans_battery_flag"):
         c_packet["rainBatteryStatus"] = values["trans_battery_flag"]
        else:
           test = values.get("trans_battery_flag", None) 
           if test != None:
             c_packet["rainBatteryStatus"] = test

        #packet["rainBatteryStatus"] = values["trans_battery_flag"]

        #if values.get("rx_state"):
        #   c_packet["signalr"] = values["rx_state"]
        c_packet["rssir"] = values["rssi_last"]
        c_packet["txIDr"] = values["tx_id"]
        c_packet["rxCheckPercentr"] = values["reception_day"]
        c_packet["packets_receivedr"] = values["packets_received_day"]
        c_packet["packets_missedr"] = values["packets_missed_day"]
        c_packet["crc_errorr"] = values["crc_errors_day"]
        c_packet["resyncsr"] = values["resyncs_day"]
        c_packet["afcr"] = values["freq_index"]

      except:
        logerr("Problem with Rain data.")

    if iss2_data:
      if self.packet_log == 7:
         loginf("iss2_data: %s" % iss2_data)
      values = iss2_data["data"][0]
      if values["temp"]:
        c_packet["windSpeed_2"] = values["wind_speed_last"]
        c_packet["windDir_2"] = values["wind_dir_last"]
        c_packet["windGust_2"] = values["wind_speed_hi_last_2_min"]
        c_packet["windGustDir_2"] = values["wind_dir_at_hi_speed_last_2_min"]
        c_packet["windSpeed1_2"] = values["wind_speed_avg_last_1_min"]
        c_packet["windDir1_2"] = values["wind_dir_scalar_avg_last_1_min"]
        c_packet["windSpeed10_2"] = values["wind_speed_avg_last_10_min"]
        c_packet["windDir10_2"] = values["wind_dir_scalar_avg_last_10_min"]
        c_packet["windGustSpeed10_2"] = values["wind_speed_hi_last_10_min"]
        c_packet["windGustDir10_2"] = values["wind_dir_at_hi_speed_last_10_min"]
        c_packet["outTemp_2"] = values["temp"]
        c_packet["outHumidity_2"] = values["hum"]
        c_packet["dewpoint2"] = values["dew_point"]
        c_packet["heatindex2"] = values["heat_index"]
        c_packet["windchill2"] = values["wind_chill"]
        c_packet["THSW_2"] = values["thsw_index"]
        c_packet["THW_2"] = values["thw_index"]
        c_packet["outWetbulb_2"] = values["wet_bulb"]
        c_packet["radiation_2"] = values["solar_rad"]
        c_packet["UV_2"] = values["uv_index"]
        c_packet["txBatteryStatus_2"] = values["trans_battery_flag"]
        c_packet["signal_2"] = values["rx_state"]
        c_packet["rssi_2"] = values["rssi_last"]
        c_packet["txID_2"] = values["tx_id"]
        c_packet["rxCheckPercent_2"] = values["reception_day"]
        c_packet["packets_received_2"] = values["packets_received_day"]
        c_packet["packets_missed_2"] = values["packets_missed_day"]
        c_packet["crc_error_2"] = values["crc_errors_day"]
        c_packet["resyncs_2"] = values["resyncs_day"]
        c_packet["supercapVolt_2"] = values["supercap_volt"]
        c_packet["solarVolt_2"] = values["solar_panel_volt"]
        c_packet["txBatteryVolt_2"] = values["trans_battery_volt"]
        c_packet["afc_2"] = values["freq_index"]

        c_packet["hdd_day_2"] = values["hdd_day"]
        if c_packet["hdd_day_2"] > 0:
           c_packet["hddc_day_2"] = 18 - ( (65 - c_packet["hdd_day_2"] - 32) * 5 / 9) 
        else:
           c_packet["hddc_day"] = 0

        c_packet["cdd_day_2"] = values["cdd_day"]
        if c_packet["cdd_day_2"] > 0:
           c_packet["cddc_day_2"] = 18 + ( (65 + c_packet["cdd_day_2"] - 32) * 5 / 9) 
        else:
           c_packet["cddc_day_2"] = 0

        test = values["rainfall_day_in"]
        if values["rainfall_day_in"] is not None:
          if self.rain2init is False:

              # Check current rain for the day and set it
              self.rain2_previous_period = values["rainfall_day_in"]

              # Set date for previous rain
              self.rain2_previous_date = datetime.datetime.fromtimestamp(self.raindatetime)
              self.rain2init = True

          if self.rain2init is True:
            c_packet["stormRain_2"] = values["rain_storm_current_in"]
            c_packet["stormRainlast_2"] = values["rain_storm_last_in"]
            c_packet["rain15_2"] = values["rainfall_last_15_min_in"]
            c_packet["rain60_2"] = values["rainfall_last_60_min_in"]
            c_packet["rain24_2"] = values["rainfall_last_24_hr_in"]
            c_packet["rain_rate_hi_last_15_min_2"] = values["rain_rate_hi_last_15_min_in"]

            c_packet["rain_storm_start_at_2"] = values["rain_storm_current_start_at"]
            c_packet["rain_storm_last_start_at_2"] = values["rain_storm_last_start_at"]
            c_packet["rain_storm_last_end_at_2"] = values["rain_storm_last_end_at"]

            c_packet["dayRain_2"] = values["rainfall_day_in"]
            c_packet["monthRain_2"] = values["rainfall_month_in"]
            c_packet["yearRain_2"] = values["rainfall_year_in"]

            c_packet["rainRate_2"] = values["rain_rate_last_in"]

            #self.calculate_rain2()

            rain2_now = values["rainfall_day_in"] - self.rain2_previous_period
            rain2_v = rain2_now

            if rain2_v >= 0:
              c_packet["rain_2"] = rain2_v
              if (self.packet_log == -1) and rain2_v > 0:
                 loginf("rain_2 %.2f mm " % (c_packet["rain_2"]*25.4))
            else: 
              if (rain2_v-test < 0) and  (abs(rain2_v) != test):
                 c_packet["rain_2"] = test
                 if (self.packet_log == -1) and (c_packet["rain_2"] > 0): 
                    loginf("rain_2abs  %.2f mm" % (c_packet["rain_2"]*25.4))
              else:
                 c_packet["rain_2"] = 0


            self.rain2_previous_period = values["rainfall_day_in"]
            self.rain2_previous_date = datetime.datetime.fromtimestamp(self.raindatetime)

        c_packet["dayET_2"] = values["et_day"]
        if values["et_day"] is not None:
           ET2_now = values["et_day"] - self.ET2_previous_period
           ET2_v = ET2_now
           if ET2_v >= 0:
              c_packet["ET_2"] = ET2_v
           else:
              c_packet["ET_2"] = 0
            
           self.ET2_previous_period = values["et_day"]
        else:
           c_packet["ET_2"] = 0

        c_packet["monthET_2"] = values["et_month"]
        c_packet["yearET_2"] = values["et_year"]

        if c_packet["outTemp_2"] is not None and c_packet["outHumidity_2"] is not None:
           c_packet["humidex1"] = weewx.wxformulas.humidexF(c_packet["outTemp_2"], c_packet["outHumidity_2"])
           if c_packet["windSpeed_2"] is not None:
              c_packet["appTemp1"] = weewx.wxformulas.apptempF(c_packet["outTemp_2"], c_packet["outHumidity_2"],c_packet["windSpeed_2"])
        if c_packet["windSpeed_2"] is not None:
           c_packet["windrun_2"] = c_packet["windSpeed_2"] * 2.5 / 60.0 #(miles)

    if airlink_data:
        if self.packet_log == 5:
           loginf("airlink_data: %s" % airlink_data)
        values = airlink_data["data"][0]

        #c_packet['last_report_time'] = values['last_report_time']
        c_packet['co2_Temp'] = values['temp']
        c_packet['co2_Hum'] = values['hum']
        c_packet['dewpoint1'] = values['dew_point']
        c_packet['wetbulb1'] = values['wet_bulb']
        c_packet['heatindex1'] = values['heat_index']
        c_packet['pct_pm_data_last_1_hour'] = values['pct_pm_data_1_hour']
        c_packet['pct_pm_data_last_3_hours'] = values['pct_pm_data_3_hour']
        c_packet['pct_pm_data_nowcast'] = values['pct_pm_data_nowcast']
        c_packet['pct_pm_data_last_24_hours'] = values['pct_pm_data_24_hour']

        if values['pm_1'] > 1000:
           c_packet['pm1_0'] = 999
        else: 
           c_packet['pm1_0'] = values['pm_1']

        if values['pm_2p5'] > 1000:
           c_packet['pm2_5'] = 999
        else:
           c_packet['pm2_5'] = values['pm_2p5']

        if values['pm_10'] > 1000:
           c_packet['pm10_0'] = 999
        else:
           c_packet['pm10_0'] = values['pm_10']

        c_packet['pm_2p5_last_1_hour'] = values['pm_2p5_1_hour']
        c_packet['pm_2p5_last_3_hours'] = values['pm_2p5_3_hour']
        c_packet['pm_2p5_last_24_hours'] = values['pm_2p5_24_hour']

        c_packet['pm_10_last_1_hour'] = values['pm_10_1_hour']
        c_packet['pm_10_last_3_hours'] = values['pm_10_3_hour']
        c_packet['pm_10_last_24_hours'] = values['pm_10_24_hour']

        c_packet['pm2_5_nowcast'] = values['pm_2p5_nowcast']
        c_packet['pm10_0_nowcast'] = values['pm_10_nowcast']

    if health_data:
        if self.health_found == False:
           loginf("Found current Health data")
           self.health_found = True

        if self.packet_log == 8:
           loginf("health_data: %s" % health_data)
        values = health_data["data"][0]

        c_packet["consoleBatteryC"] = values["battery_voltage"]
        c_packet["rssiC"] = values["wifi_rssi"]
        c_packet["consoleApiLevelC"] = values["console_api_level"]
        c_packet["queueKilobytesC"] = values["queue_kilobytes"]
        c_packet["freeMemC"] = values["free_mem"]
        c_packet["systemFreeSpaceC"] = values["system_free_space"]
        c_packet["chargerPluggedC"] = values["charger_plugged"]
        c_packet["batteryPercentC"] = values["battery_percent"]
        c_packet["localAPIQueriesC"] = values["local_api_queries"]
        c_packet["healthVersionC"] = values["health_version"]
        c_packet["linkUptimeC"] = values["link_uptime"]
        c_packet["rxKilobytesC"] = values["rx_kilobytes"]
        c_packet["connectionUptimeC"] = values["connection_uptime"]
        c_packet["osUptimeC"] = values["os_uptime"]
        c_packet["batteryConditionC"] = values["battery_condition"]
        c_packet["iFreeSpaceC"] = values["internal_free_space"]
        c_packet["batteryCurrentC"] = values["battery_current"]
        c_packet["batteryStatusC"] = values["battery_status"]
        c_packet["databaseKilobytesC"] = values["database_kilobytes"]
        c_packet["batteryCycleCountC"] = values["battery_cycle_count"]
        c_packet["bootloaderVersionC"] = values["bootloader_version"]
        c_packet["clockSourceC"] = values["clock_source"]
        c_packet["appUptimeC"] = values["app_uptime"]
        c_packet["batteryTempC"] = values["battery_temp"]
        c_packet["txKilobytesC"] = values["tx_kilobytes"]
        c_packet["consoleRadioVersionC"] = values["console_radio_version"]
        c_packet["consoleSwVersionC"] = values["console_sw_version"]
        c_packet["consoleOsVersionC"] = values["console_os_version"]


    if airlinkhealth_data:
        if self.airlinkhealth_found == False:
           loginf("Found current Airlink Health data")
           self.airlinkhealth_found = True

        if self.packet_log == 8:
           loginf("airlinkhealth_data: %s" % airlinkhealth_data)
        values = airlinkhealth_data["data"][0]

        c_packet["rssiA"] = values["wifi_rssi"]
        c_packet["firmwareVersionA"] = values["firmware_version"]
        #test = values["bootloader_version"]
        #if test != None:
        #   if test < 1000000000:
        #      test = test + 1000000000
        #c_packet["bootloaderVersionA"] = test
        c_packet["bootloaderVersionA"] = values["bootloader_version"]
        c_packet["iFreeMemChunkA"] = values["internal_free_mem_chunk_size"]
        c_packet["iUsedMemA"] = values["internal_used_mem"]
        c_packet["iFreeMemA"] = values["internal_free_mem"]
        c_packet["tUsedMemA"] = values["total_used_mem"]
        c_packet["tFreeMemA"] = values["total_free_mem"]
        c_packet["iFreeMemWatermA"] = values["internal_free_mem_watermark"]
        c_packet["errorPacketsA"] = values["packet_errors"]
        c_packet["droppedPacketsA"] = values["dropped_packets"]
        c_packet["rxPacketsA"] = values["rx_packets"]
        c_packet["txPacketsA"] = values["tx_packets"]
        c_packet["recordWriteCountA"] = values["record_write_count"]
        c_packet["localAPIQueriesA"] = values["local_api_queries"]
        c_packet["uptimeA"] = values["uptime"]
        c_packet["linkUptimeA"] = values["link_uptime"]
        c_packet["healthVersionA"] = values["health_version"]


    return c_packet

class DavisConsoleApi(StdService):
    """Collect Davis sensor information."""

    def __init__(self, engine, config_dict):
        super(DavisConsoleAPI, self).__init__(engine, config_dict)
        loginf("Version is %s" % DRIVER_VERSION)

        options = config_dict.get("DavisConsoleAPI", {})

        #self.polling_interval = 300  # default = 300
        self.polling_interval = weeutil.weeutil.to_int(options.get("polling_interval", 300))
        if self.polling_interval < 60:
           self.polling_interval = 60
        loginf("polling interval is %s" % self.polling_interval)

        self.api_key = options.get("api_key", None)
        self.api_secret = options.get("api_secret", None)
        self.station_id = options.get("station_id", None)
        self.packet_log = weeutil.weeutil.to_int(options.get("packet_log", 0))
 
        self.max_count = 0
        self.found = False

        self.raininit = False
        self.rain2init = False
        self.rain_previous_period = 0
        self.rain2_previous_period = 0

        self.ET_previous_period = 0
        self.ET2_previous_period = 0

        self.iss_found = False
        self.iss2_found = False
        self.extra1_found = False
        self.extra2_found = False
        self.extra3_found = False
        self.extra4_found = False
        self.leaf_found = False
        self.soil_found = False
        self.leaf_soil_found = False
        self.wind_found = False
        self.rain_found = False
        self.health_found = False
        self.airlink_found = False
        self.airlinkhealth_found = False
        
        self.txid_iss = weeutil.weeutil.to_int(options.get("txid_iss", None))
        if self.txid_iss == None:
           self.txid_iss = 1
        self.txid_iss2 = weeutil.weeutil.to_int(options.get("txid_iss2", None))
        self.txid_extra1 = weeutil.weeutil.to_int(options.get("txid_extra1", None))
        self.txid_extra2 = weeutil.weeutil.to_int(options.get("txid_extra2", None))
        self.txid_extra3 = weeutil.weeutil.to_int(options.get("txid_extra3", None))
        self.txid_extra4 = weeutil.weeutil.to_int(options.get("txid_extra4", None))
        self.txid_leaf_soil = weeutil.weeutil.to_int(stn_dict.get("txid_leaf_soil", None))
        self.txid_leaf = weeutil.weeutil.to_int(options.get("txid_leaf", None))
        self.txid_soil = weeutil.weeutil.to_int(options.get("txid_soil", None))
        self.txid_wind = weeutil.weeutil.to_int(options.get("txid_wind", None))
        self.txid_rain = weeutil.weeutil.to_int(options.get("txid_rain", None))
        self.airlink = weeutil.weeutil.to_int(stn_dict.get("airlink", 0))

        # get the database parameters we need to function
        binding = options.get("data_binding", "wx_binding")
        self.dbm = self.engine.db_binder.get_manager(
            data_binding=binding, initialize=True
        )

        # be sure schema in database matches the schema we have
        dbcol = self.dbm.connection.columnsOf(self.dbm.table_name)
        dbm_dict = weewx.manager.get_manager_dict(
            config_dict["DataBindings"], config_dict["Databases"], binding
        )
        #memcol = [x[0] for x in dbm_dict["schema"]]
        #if dbcol != memcol:
        #    raise Exception(
        #        "davisconsoleapi schema mismatch: %s != %s" % (dbcol, memcol)
        #    )

        self.last_ts = None
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

    @staticmethod
    def get_data(self):
        """Make an API call and process the data"""
        packet = dict()
        packet["dateTime"] = int(time.time())
        self.raindatetime = int(time.time())
        packet["usUnits"] = weewx.US

        if not self.api_key or not self.station_id or not self.api_secret:
            logerr(
                "davisconsoleapi is missing a required parameter. "
                "Double-check your configuration file. key: %s"
                "secret: %s station ID: %s" % (self.api_key, self.api_secret, self.station_id)
            )
            return packet

        # WL API expects all of the components of the API call to be in
        # alphabetical order before the signature is calculated
        parameters = {
            "api-key": self.api_key,
            "end-timestamp": int(time.time()),
            "start-timestamp": int(time.time() - self.polling_interval),
            "station-id": self.station_id,
            "t": int(time.time()),
        }
        
        uerror = False
        c_error = False
        url = get_current_url(parameters, self.api_secret)
        logdbg("Current data url is %s" % url)
        data = get_json(url, uerror)
        if 'API rate limit exceeded' in data:
          uerror = True
          logerr("Error: %s" % 'API rate limit exceeded')
        if uerror == False: 
          if self.packet_log == 9:
            loginf("all_c_data: %s" % data)
          c_packet = decode_current_json(data, self)
        else:
          c_error = True  
        #if not h_error:
        #   packet.update(h_packet)
        
        packet["dateTime"] = self.ts

        if not c_error:
           packet.update(c_packet)

        return packet

    def shutDown(self):
        """close database"""
        try:
            self.dbm.close()
        except Exception as error:
            logerr("Database exception: %s" % error)

    def new_archive_record(self, event):
        """save data to database"""
        now = int(time.time() + 0.5)
        delta = now - event.record["dateTime"]
        self.last_ts = event.record["dateTime"]
        if delta > event.record["interval"] * 60:
            loginf("Skipping record: time difference %s too big" % delta)
            return

        if self.last_ts is not None:
            self.save_data(self.get_packet(now, self.last_ts))
        self.last_ts = now

    def save_data(self, record):
        """save data to database"""
        self.dbm.addRecord(record)

    def get_packet(self, now_ts, last_ts):
        """Retrieves and assembles the final packet"""
        record = self.get_data(self)
        # calculate the interval (an integer), and be sure it is non-zero
        #record["interval"] = max(1, int((now_ts - last_ts) / 60))

        record["interval"] = 5
        #loginf("interval record:  %s " % int((now_ts - last_ts) / 60))
        logdbg("davisconsoleapi packet: %s" % record)

        return record




class Console:
    def __init__(self):
        
        self.davis_date_stamp = None
        self.system_date_stamp = None

        self.davis_packet = dict()
        self.davis_packet['rain'] = 0


class DavisConsoleAPIDriver(weewx.drivers.AbstractDevice):
    """weewx driver that reads data from a WeatherLink Console
    """

    def __init__(self, **stn_dict):

        # Show Diver version
        loginf('DavisConsoleAPI driver version is %s' % DRIVER_VERSION)

        #self.station = Console()

        #self.polling_interval = 300  # default = 300
        self.polling_interval = weeutil.weeutil.to_int(stn_dict.get("polling_interval", 300))
        if self.polling_interval < 60:
           self.polling_interval = 60
        loginf("polling interval is %s" % self.polling_interval)

        self.api_key = stn_dict.get("api_key", None)
        self.api_secret = stn_dict.get("api_secret", None)
        self.station_id = stn_dict.get("station_id", None)
        self.packet_log = weeutil.weeutil.to_int(stn_dict.get("packet_log", 0))

        self.max_count = 0
        self.found = False
        self.firststart = True

        self.raininit = False
        self.rain2init = False
        self.rain_previous_period = 0
        self.rain2_previous_period = 0

        self.ET_previous_period = 0
        self.ET2_previous_period = 0

        self.iss_found = False
        self.iss2_found = False
        self.extra1_found = False
        self.extra2_found = False
        self.extra3_found = False
        self.extra4_found = False
        self.leaf_found = False
        self.soil_found = False
        self.leaf_soil_found = False
        self.wind_found = False
        self.rain_found = False
        self.health_found = False
        self.airlink_found = False
        self.airlinkhealth_found = False
        
        self.txid_iss = weeutil.weeutil.to_int(stn_dict.get("txid_iss", None))
        if self.txid_iss == None:
           self.txid_iss = 1
        self.txid_iss2 = weeutil.weeutil.to_int(stn_dict.get("txid_iss2", None))
        self.txid_extra1 = weeutil.weeutil.to_int(stn_dict.get("txid_extra1", None))
        self.txid_extra2 = weeutil.weeutil.to_int(stn_dict.get("txid_extra2", None))
        self.txid_extra3 = weeutil.weeutil.to_int(stn_dict.get("txid_extra3", None))
        self.txid_extra4 = weeutil.weeutil.to_int(stn_dict.get("txid_extra4", None))
        self.txid_leaf_soil = weeutil.weeutil.to_int(stn_dict.get("txid_leaf_soil", None))
        self.txid_leaf = weeutil.weeutil.to_int(stn_dict.get("txid_leaf", None))
        self.txid_soil = weeutil.weeutil.to_int(stn_dict.get("txid_soil", None))
        self.txid_wind = weeutil.weeutil.to_int(stn_dict.get("txid_wind", None))
        self.txid_rain = weeutil.weeutil.to_int(stn_dict.get("txid_rain", None))
        self.airlink = weeutil.weeutil.to_int(stn_dict.get("airlink", 0))


    @property
    def hardware_name(self):
        return "DavisConsoleAPI"

    @staticmethod
    def get_data(self):
        """Make an API call and process the data"""
        packet = dict()
        packet["dateTime"] = int(time.time())
        self.raindatetime = int(time.time())
        packet["usUnits"] = weewx.US

        if not self.api_key or not self.station_id or not self.api_secret:
            logerr(
                "davisconsoleapi is missing a required parameter. "
                "Double-check your configuration file. key: %s"
                "secret: %s station ID: %s" % (self.api_key, self.api_secret, self.station_id)
            )
            return packet

        # Davis API2 expects all of the components of the API call to be in
        # alphabetical order before the signature is calculated
        parameters = {
            "api-key": self.api_key,
            "end-timestamp": int(time.time()),
            "start-timestamp": int(time.time() - self.polling_interval),
            "station-id": self.station_id,
            "t": int(time.time()),
        }


        uerror = False

        #h_error = False
        #url = get_historical_url(parameters, self.api_secret)
        #logdbg("Historical data url is %s" % url)
        #data = get_json(url, uerror)
        #if 'API rate limit exceeded' in data:
        #  loginf("API2 error: %s" % data)
        #  uerror = True
        #if uerror == False: 
        #  if self.packet_log = 10:
        #    loginf("h_data: %s" % data)
        #  if self.packet_log >= 3:
        #     test = ("h_data: %s" % data)
        #     loginf("h_data_len: %s" % len(test))
        #  h_packet = decode_historical_json(data, self)
        #else:
        #  h_error = True 

        c_error = False
        url = get_current_url(parameters, self.api_secret)
        logdbg("Current data url is %s" % url)
        data = get_json(url, uerror)
        #if "API rate limit exceeded" in data:
        #  loginf("API2 error: %s" % data)
        #  uerror = True

        if uerror == False: 
          if self.packet_log >= 9:
            loginf("all_c_data: %s" % data)
          c_packet = decode_current_json(data, self)
        else:
          c_error = True  

        #if not h_error:
        #   packet.update(h_packet)
        
        #packet["dateTime"] = self.ts
        logdbg("all_data: %s" % packet)

        if not c_error:
           packet.update(c_packet)
           #if self.ts is not None:
           # packet["dateTime"] = self.ts
        return packet

    def test_midnight(self):
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M:%S")
        start = '00:00:00'
        end = '00:00:05'
        if start < current_time < end:
            logdbg('Midnight nap')
            logdbg(current_time)
            return True
        else:
            return False

    def genLoopPackets(self):

        # Start Loop
        self.start = True
        self.timeout = time.time()
        now = int(time.time() + 0.5)  
        if self.packet_log >= 1:
           testtime = self.polling_interval - (self.timeout % self.polling_interval)
           loginf("Start Loop %s sec" % int(testtime))

        
        while True:
            
              while (self.timeout < time.time()):

                now = int(time.time() + 0.5)
                testtime = int(self.polling_interval - (now % self.polling_interval))
                if testtime > 210:
                   testtime = 150

                if (self.packet_log >= 1) and self.start == False:
                   loginf("Archive %s sec" % (testtime))

                #time.sleep(60)
                self.start = False


                #delta = now - event.record["dateTime"]
                #self.last_ts = event.record["dateTime"]
 
                record = self.get_data(self)
                packet = record
                if (self.packet_log >= 1 or self.firststart is True) and self.ts is not None:
                   loginf('CurrentData Time {} '.format(weeutil.weeutil.timestamp_to_string(self.ts)))
                if (self.packet_log >= 1 or self.firststart is True) and self.tshealth is not None:
                   loginf('Health Data Time {} '.format(weeutil.weeutil.timestamp_to_string(self.tshealth)))


                self.last_ts = now

                yield packet
                self.timeout = time.time() + (testtime + 3)
                if self.ts is not None:
                     self.firststart = False

# To test this driver, run it directly as follows:
#   PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/davisconsoleapi.py
#   for RasPi:  PYTHONPATH=/usr/share/weewx python3 /usr/share/weewx/user/davisconsoleapi.py
#
if __name__ == "__main__":
    import optparse

    import weeutil.logger
    import weewx

    weewx.debug = 1
    weeutil.logger.setup('DavisConsoleAPI', {})

    usage = """Usage:%prog [--help] [--version]"""

    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--version', dest='version', action='store_true',
                      help='Display driver version')
    #
    (options, args) = parser.parse_args()

    if options.version:
        print("Davis Console Api Driver version %s" % DRIVER_VERSION)
        exit(0)

    driver = DavisConsoleAPIDriver()
    for packet in driver.genLoopPackets():
        print(weeutil.weeutil.timestamp_to_string(packet['dateTime']), packet)

