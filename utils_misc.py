import time

def wait_for_output(func, timeout, first=0.0, step=1.0):
    end_time = time.time() + float(timeout)
    time.sleep(first)

    while time.time() < end_time:
        output = func()
        if output:
            return output
        time.sleep(step)

    return None

def py3_to_str(bytes_or_str):
    if isinstance(bytes_or_str, bytes):
        value = bytes_or_str.decode('utf-8')
    else:
        value = bytes_or_str
    return value

def py3_to_bytes(bytes_or_str):
    if isinstance(bytes_or_str, str):
        value = bytes_or_str.encode('utf-8')
    else:
        value = bytes_or_str
    return value

def py2_to_unicode(unicode_or_str):
    if isinstance(unicode_or_str, str):
        value = unicode(unicode_or_str, 'utf-8')
    else:
        value = unicode_or_str
    return value

def py2_to_srt(unicode_or_str):
    if isinstance(unicode_or_str, unicode):
        value = unicode_or_str.encode('utf-8')
    else:
        value = unicode_or_str
    return value