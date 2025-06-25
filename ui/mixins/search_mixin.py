"""为音乐列表提供简单名称搜索功能的混入类。"""

import os
class SearchMixin:
    """提供搜索能力的混入类。"""

    def search_songs(self):
        """根据搜索框内容过滤歌曲列表。"""
        query = self.search_var.get().lower()
        if not query:
            self.music_files = list(self.all_music_files)
        else:
            self.music_files = [
                f for f in self.all_music_files if query in os.path.basename(f).lower()
            ]
        self.refresh_file_listbox()

