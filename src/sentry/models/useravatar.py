from __future__ import absolute_import

import uuid

from PIL import Image

from django.db import models

from sentry.db.models import FlexibleForeignKey, Model
from sentry.utils.cache import cache
from sentry.utils.compat import StringIO


class UserAvatar(Model):
    """
    A UserAvatar associates a User with their avatar photo File
    and contains their preferences for avatar type.
    """
    __core__ = False

    AVATAR_TYPES = (
        ('letter_avatar', 'LetterAvatar'),
        ('upload', 'Upload'),
        ('gravatar', 'Gravatar'),
    )

    ALLOWED_SIZES = (20, 48, 52, 64, 80, 96)

    user = FlexibleForeignKey('sentry.User', unique=True, related_name='avatar')
    file = FlexibleForeignKey('sentry.File', unique=True, null=True, on_delete=models.SET_NULL)
    ident = models.CharField(max_length=36, unique=True, db_index=True, null=True)
    avatar_type = models.CharField(max_length=20, choices=AVATAR_TYPES, default='letter_avatar')

    class Meta:
        app_label = 'sentry'
        db_table = 'sentry_useravatar'

    def save(self, *args, **kwargs):
        if not self.ident:
            self.ident = uuid.uuid4()
        return super(UserAvatar, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.file:
            self.file.delete()
        return super(UserAvatar, self).delete(*args, **kwargs)

    def get_cache_key(self, size):
        return 'avatar:%s:%s' % (self.user_id, size)

    def clear_cached_photos(self):
        cache.delete_many(map(self.get_cache_key, self.ALLOWED_SIZES))

    def get_cached_photo(self, size):
        if not self.file:
            return
        if size not in self.ALLOWED_SIZES:
            size = min(self.ALLOWED_SIZES, key=lambda x: abs(x - size))
        cache_key = self.get_cache_key(size)
        photo = cache.get(cache_key)
        if not photo:
            photo_file = self.file.getfile()
            with Image.open(photo_file) as image:
                image = image.resize((size, size))
                image_file = StringIO()
                image.save(image_file, 'PNG')
                photo_file = image_file.getvalue()
                cache.set(cache_key, photo_file)
                photo = cache.get(cache_key)
        return photo
