import os
class SearchMixin:
    """Mixin providing search capability."""

    def search_songs(self):
        query = self.search_var.get().lower()
        if not query:
            self.music_files = list(self.all_music_files)
        else:
            self.music_files = [
                f for f in self.all_music_files if query in os.path.basename(f).lower()
            ]
        self.refresh_file_listbox()

