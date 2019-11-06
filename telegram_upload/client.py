import getpass
import json
import re
from distutils.version import StrictVersion
from typing import Iterable

import click
import os

from telethon.tl.types import Message, DocumentAttributeFilename
from telethon.utils import pack_bot_file_id

from telegram_upload.files import get_file_attributes, get_file_thumb
from telethon.version import __version__ as telethon_version
from telethon import TelegramClient

if StrictVersion(telethon_version) >= StrictVersion('1.0'):
    import telethon.sync


CAPTION_MAX_LENGTH = 200


def phone_match(value):
    match = re.match(r'\+?[0-9.()\[\] \-]+', value)
    if match is None:
        raise ValueError('{} is not a valid phone'.format(value))
    return value


def get_progress_bar(action, file, length):
    bar = click.progressbar(label='{} {}'.format(action, file), length=length)

    def progress(current, total):
        bar.pos = 0
        bar.update(current)
    return progress


class Client(TelegramClient):
    def __init__(self, config_file, **kwargs):
        config = json.load(open(config_file))
        super().__init__(config.get('session', 'telegram-upload'), config['api_id'], config['api_hash'], **kwargs)

    def start(
            self,
            phone=lambda: click.prompt('Please enter your phone', type=phone_match),
            password=lambda: getpass.getpass('Please enter your password: '),
            *,
            bot_token=None, force_sms=False, code_callback=None,
            first_name='New User', last_name='', max_attempts=3):
        return super().start(phone=phone, password=password, bot_token=bot_token, force_sms=force_sms,
                             first_name=first_name, last_name=last_name, max_attempts=max_attempts)

    def send_files(self, entity, files, delete_on_success=False, print_file_id=False):
        for file in files:
            progress = get_progress_bar('Uploading', os.path.basename(file), os.path.getsize(file))
            name = '.'.join(os.path.basename(file).split('.')[:-1])
            thumb = get_file_thumb(file)
            caption = (name[:CAPTION_MAX_LENGTH] + '..') if len(name) > CAPTION_MAX_LENGTH else name
            try:
                attributes = get_file_attributes(file)
                message = self.send_file(entity, file, thumb=thumb,
                                         caption=caption,
                                         progress_callback=progress, attributes=attributes)
            except Exception:
                raise
            finally:
                if thumb:
                    os.remove(thumb)
            click.echo()
            if print_file_id:
                click.echo('Uploaded successfully "{}" (file_id {})'.format(file, pack_bot_file_id(message.media)))
            if delete_on_success:
                click.echo('Deleting {}'.format(file))
                os.remove(file)

    def find_files(self, entity):
        for message in self.iter_messages(entity):
            if message.document:
                yield message
            else:
                break

    def download_files(self, entity, messages: Iterable[Message], delete_on_success: bool = False):
        messages = reversed(list(messages))
        for message in messages:
            filename_attr = next(filter(lambda x: isinstance(x, DocumentAttributeFilename),
                                        message.document.attributes), None)
            filename = filename_attr.file_name if filename_attr else 'Unknown'
            progress = get_progress_bar('Downloading', filename, message.document.size)
            self.download_media(message, progress_callback=progress)
            if delete_on_success:
                self.delete_messages(entity, [message])
            print()
