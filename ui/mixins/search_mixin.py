"""Mixin adding simple name-based search to the music list."""

import os
class SearchMixin:
    """Mixin providing search capability."""

    def search_songs(self):
        """Filter the song list based on the text entered in the search box."""
        query = self.search_var.get().lower()
        if not query:
            self.music_files = list(self.all_music_files)
        else:
            self.music_files = [
                f for f in self.all_music_files if query in os.path.basename(f).lower()
            ]
        self.refresh_file_listbox()

