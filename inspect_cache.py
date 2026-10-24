import pickle
import os

if os.path.exists('lyrics_cache.pkl'):
    with open('lyrics_cache.pkl', 'rb') as f:
        cache = pickle.load(f)
        if cache:
            print(f'Total cached songs: {len(cache)}')
            for song_id, cached_data in cache.items():
                print(f'\nSong ID: {song_id}')
                print(f'Cache type: {type(cached_data)}')

                if isinstance(cached_data, dict):
                    print(f'Cache keys: {list(cached_data.keys())}')
                    lyrics = cached_data.get('lyrics', [])
                else:
                    lyrics = cached_data

                if lyrics and len(lyrics) > 0:
                    print(f'Number of lyrics: {len(lyrics)}')

                    # Check if lyrics have actual translations
                    english_count = 0
                    translated_count = 0
                    same_count = 0

                    for lyric in lyrics[:5]:  # Check first 5 lyrics
                        original = lyric.get('words', '').strip()
                        translated = lyric.get('translated', '').strip()

                        if original and translated:
                            if original == translated:
                                same_count += 1
                            else:
                                translated_count += 1
                                print(f'Translated: "{original}" -> "{translated}"')
                        elif original:
                            english_count += 1

                    print(f'Status: {translated_count} translated, {same_count} same, {english_count} missing translation')

                    # Show first lyric details
                    first_lyric = lyrics[0]
                    print(f'First lyric: {first_lyric}')
                else:
                    print('No lyrics in cache')
        else:
            print('Cache is empty')
else:
    print('No cache file found')
