import os

current_dir = os.path.dirname(os.path.realpath(__file__))
assets_dir = os.path.join(os.path.dirname(current_dir), 'assets')

def get_asset(type, filename):
    if type == 'image' or type == 'img':
        return os.path.join(assets_dir, 'imgs', filename)
    elif type == 'font' or type == 'fonts':
        return os.path.join(assets_dir, 'fonts', filename)
    else:
        raise ValueError("Type must be either 'image' or 'font'")


TOTAL_WORKERS = [None]
def get_workers():
    if TOTAL_WORKERS[0] is None:
        workers= os.getenv('WATTPAD_MAX_WORKERS', '10')
        TOTAL_WORKERS[0] = int(workers) # type: ignore
    return TOTAL_WORKERS[0] 