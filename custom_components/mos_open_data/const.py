"""Constants for mos_open_data."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "mos_open_data"

ATTRIBUTION = "Данные предоставлены порталом Открытых данных Москвы (data.mos.ru)"

CONF_ADDRESS = "address"
CONF_API_KEY = "api_key"

API_BASE_URL = "https://apidata.mos.ru/v1"

DATASET_HOT_WATER = "1401"

UPDATE_INTERVAL_SECONDS = 6 * 60 * 60
