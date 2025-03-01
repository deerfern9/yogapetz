import os
import sys
import random
import itertools
from functools import partial

import asyncio
import inquirer
from termcolor import colored
from inquirer.themes import load_theme_from_dict as loadth

from data.config import ACCOUNTS, PROXYS, CODES, logger, DB, PRIVATE_KEYS, NFT_STATS
from utils.policy import set_windows_event_loop_policy
from utils.validate_token import validate_token
from utils.db_func import process_tasks, clear_complete
from utils.create_files import create_files
from tasks.twitter_client import start_twitter_task
from data.settings import ASYNC_SEMAPHORE
from utils.show_stats import read_and_summarize_nft_stats


async def start_limited_task(semaphore, token, data, choice, spare_ref_codes=None):
    async with semaphore:
        await start_twitter_task(token, data, choice, spare_ref_codes)


def get_accounts_info(path): 
    with open(path, 'r', encoding='utf-8-sig') as file:
        if path == ACCOUNTS:
            info: list[str] = [validate_token(input_string=row.strip()) for row in file]
        else:
            info: list[str] = [row.strip() for row in file]
    return info


def get_action() -> str:
    """ Пользователь выбирает действие через меню"""

    # Тема
    theme = {
        'Question': {
            'brackets_color': 'bright_yellow'
        },
        'List': {
            'selection_color': 'bright_blue'
        },
    }

    # Варианты для выбора
    question = [
        inquirer.List(
            "action",
            message=colored('Выберете ваше действие', 'light_yellow'),
            choices=[
                '   1) Регистрация и cтартовые задачи',
                '   2) Ежедевные задачи',
                '   3) Минт книг у мастера квестов',
                '   4) Собрать реф коды',
                '   5) Собрать статистику (сминченные книги) и записать в csv file',
                '   6) Вывести статистику',
            ]
        )
    ]
    return inquirer.prompt(question, theme=loadth(theme))['action']


def run_async_task(token, data, сhoise):
    asyncio.run(start_twitter_task(token, data, сhoise))


def account_randomiser(semaphore, db, option):
    db_list = [partial(start_limited_task, semaphore, token, data, option) for token, data in db.items()]
    random.shuffle(db_list)
    return db_list

async def main():
    accounts_list: list[str] = get_accounts_info(ACCOUNTS)
    proxies_list: list[str] = get_accounts_info(PROXYS)
    ref_codes: list[str] = get_accounts_info(CODES)
    private_keys: list[str] = get_accounts_info(PRIVATE_KEYS)

    cycled_proxies_list = itertools.cycle(proxies_list) if proxies_list else None
    
    formatted_accounts_list: list = [
        {
            'account_token': current_account,
            'account_proxy': next(cycled_proxies_list) if cycled_proxies_list else None,
            'ref_code': None,
            'private_key': private_keys.pop(0) if private_keys else None
        } for current_account in accounts_list
    ]

    db, len_db = await process_tasks(file_path=DB, source_data=formatted_accounts_list)

    logger.info(f'Загружено в accounts.txt {len(accounts_list)} аккаунтов \n'
                f'\t\t\t\t\t\t\tЗагружено в proxys.txt {len(proxies_list)} прокси \n'
                f'\t\t\t\t\t\t\tЗагружено в базу данных {len_db} токенов \n')

    if len_db == 0 and not formatted_accounts_list:
        logger.error('Вы не добавили токены в необходимый файл и в базе данных тоже пусто!')
        sys.exit(1)

    user_choice = get_action()
    
    semaphore = asyncio.Semaphore(ASYNC_SEMAPHORE)

    if user_choice == '   1) Регистрация и cтартовые задачи':
        actual_to_work = await clear_complete(db)

        if len(actual_to_work) == 0:
            logger.success('Все аккаунты успешно закончили работу! Везде статус заданий - сompleted')
            sys.exit(1)
        
        logger.info(f'{len(actual_to_work)} аккаунтов еще не выполнили начальные задачи.. Начинаем. Игнорируется SUSPENDED и BAD_TOKEN')
        logger.info(f'Все проблемные акки будут записаны в problems.txt')
        
        
        tasks = []
        for token, data in actual_to_work.items():
            task = asyncio.create_task(start_limited_task(semaphore, token, data, 1, spare_ref_codes=ref_codes))
            tasks.append(task)

        await asyncio.wait(tasks)

    elif user_choice == '   2) Ежедевные задачи':
        
        db_list = account_randomiser(semaphore, db, option=1)
        tasks = [asyncio.create_task(account()) for account in db_list]
        await asyncio.wait(tasks)

    elif user_choice == '   3) Минт книг у мастера квестов':
        db_list = account_randomiser(semaphore, db, option=3)

        tasks = [asyncio.create_task(account()) for account in db_list]
        await asyncio.wait(tasks)

    elif user_choice == '   4) Собрать реф коды':
        db_list = account_randomiser(semaphore, db, option=4)

        tasks = [asyncio.create_task(account()) for account in db_list]
        await asyncio.wait(tasks)

    elif user_choice == '   5) Собрать статистику (сминченные книги) и записать в csv file':
        os.remove(NFT_STATS)
        db_list = account_randomiser(semaphore, db, option=5)

        tasks = [asyncio.create_task(account()) for account in db_list]
        await asyncio.wait(tasks)
        read_and_summarize_nft_stats(NFT_STATS)

    elif user_choice == '   6) Вывести статистику':
        read_and_summarize_nft_stats(NFT_STATS)
    
if __name__ == '__main__':
    create_files()
    set_windows_event_loop_policy()
    asyncio.run(main())
