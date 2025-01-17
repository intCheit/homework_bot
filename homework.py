import logging
import os
import sys
import time
from contextlib import suppress
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


class APIRequestError(ConnectionError):
    """Исключение для ошибок при запросе к API."""

    pass


def check_tokens():
    """Проверяет наличие всех необходимых переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    missing_tokens = [name for name, value in tokens.items() if not value]
    if missing_tokens:
        missing = ', '.join(missing_tokens)
        logging.critical(
            f"Отсутствуют обязательные переменные окружения: {missing}"
        )
        raise EnvironmentError(
            f"Отсутствуют обязательные переменные окружения: {missing}"
        )


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    bot.send_message(TELEGRAM_CHAT_ID, message)
    logging.debug(f'Бот отправил сообщение: "{message}"')


def get_api_answer(timestamp):
    """Делает запрос к API."""
    logging.debug(
        f'Отправка запроса к API. URL: {ENDPOINT}, параметры: {{"from_date": {timestamp}}}'
    )

    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        raise APIRequestError(
            f'Сбой при запросе к API. Эндпоинт: {ENDPOINT}, '
            f'параметры: {{"from_date": {timestamp}}}. Ошибка: {error}'
        )

    if response.status_code != HTTPStatus.OK:
        raise APIRequestError(
            f'Эндпоинт недоступен. Код ответа: {response.status_code}. '
            f'URL: {ENDPOINT}, параметры: {{"from_date": {timestamp}}}'
        )

    try:
        return response.json()
    except ValueError as error:
        raise ValueError(
            f'Ошибка преобразования ответа в JSON. Эндпоинт: {ENDPOINT}, '
            f'параметры: {{"from_date": {timestamp}}}, ошибка: {error}'
        )


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API не является словарём, получен тип: {type(response).__name__}'
        )
    if 'homeworks' not in response:
        raise KeyError(
            'Отсутствует ключ "homeworks" в ответе API'
        )
    if not isinstance(response['homeworks'], list):
        raise TypeError(
            f'Тип данных "homeworks" не является списком, получен тип: {type(response["homeworks"]).__name__}'
        )
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус работы."""
    missing_keys = [key for key in ('homework_name', 'status') if key not in homework]
    if missing_keys:
        raise KeyError(
            f'Отсутствуют ключи в ответе API: {", ".join(missing_keys)}'
        )
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус работы: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error = ""
    last_message = ""

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logging.debug('Отсутствуют новые статусы в ответе API')
                time.sleep(RETRY_PERIOD)
                continue

            # Обработка первого элемента списка homeworks
            homework = homeworks[0]
            message = parse_status(homework)

            if message != last_message:
                send_message(bot, message)
                last_message = message

            timestamp = response.get('current_date', timestamp)
        except ApiTelegramException as tg_error:
            logging.error(f'Ошибка Telegram API: {tg_error}')
        except (APIRequestError, Exception) as error:
            error_message = f'Сбой в работе программы: {error}'
            logging.error(error_message)
            if last_error != str(error):
                with suppress(Exception):
                    send_message(bot, error_message)
                last_error = str(error)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, %(levelname)s, %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    main()
