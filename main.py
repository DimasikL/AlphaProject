from stream_interceptor import StreamInterceptor
from llm_simulator import simulate_llm_stream

mapping = {'[PER_1]': 'Иванов Пётр', '[PHONE_1]': '+7 999 123-45-67'}
interceptor = StreamInterceptor(mapping)

llm_response = 'Здравствуйте, [PER_1]! Ваш номер [PHONE_1]. Чем могу помочь?'
print('Клиент видит: ', end='', flush=True)
for chunk in simulate_llm_stream(llm_response, min_chunk=1, max_chunk=3):
    clean = interceptor.feed(chunk)
    if clean:
        print(clean, end='', flush=True)
print(interceptor.flush())
print(f'\nСтатистика: {interceptor.stats}')
