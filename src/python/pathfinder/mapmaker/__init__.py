import logging
import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from os import scandir, stat
from os.path import dirname, basename, abspath, isfile
from pathlib import Path

from PIL import Image, ImageEnhance
from fpdf import FPDF

TORCH_PATH = None
WAIFU2X_LUA_PATH = None
WAIFU2X_MACOS_PATH = None


def parse_filename(filename):
    """
    Parse a filename of the form name_WWxHH.png, i.e. deep_canyon_10x18.png, into a set of useful properties. Returns
    a tuple containing the canonical filename supplied, the canonical name of the pdf to produce, the plain name with
    the sizes stripped, and the width and height specified.

    :param filename:
        Filename to parse
    :return:
        A tuple of (filename, pdf_name, name, width, height)
    :raise:
        ValueError if the string can't be parsed in this format
    """
    filename = abspath(filename)
    leaf_name = basename(filename)
    # Match in the form foo_bar_12.4x25.3.png and extract the name, 12.4, and 25.3 bits
    m = re.match(r'(^\w+?)_*(\d+(?:\.\d*)?|\.\d+)x(\d+(?:\.\d*)?|\.\d+)\.png$',
                 leaf_name)
    if m:
        name = m.groups()[0]
        width = float(m.groups()[1])
        height = float(m.groups()[2])
        pdf_name = dirname(filename) + '/' + name + '.pdf'
        return filename, pdf_name, name, width, height
    else:
        raise ValueError('Filename not of the form name_WxH.png, was {}'.format(leaf_name))


@dataclass
class PaperSize:
    """
    Defines a paper size
    """
    width: int
    height: int
    name: str


class Paper(Enum):
    """
    Common paper sizes, used by the split_image and make_pdf functions to determine how images should be tiled across
    the available paper space.
    """

    A4 = PaperSize(height=297, width=210, name='A4')
    A3 = PaperSize(height=420, width=297, name='A3')
    A2 = PaperSize(height=594, width=420, name='A2')
    A1 = PaperSize(height=841, width=594, name='A1')
    A0 = PaperSize(height=1189, width=841, name='A0')

    @property
    def dimensions(self):
        return self.width, self.height

    @property
    def width(self):
        return self.value.width

    @property
    def height(self):
        return self.value.height

    @property
    def name(self):
        return self.value.name

def basic_image_ops(image, brighten=1.0, sharpen=None, saturation=None):
    """
    Perform basic brighten, sharpen, colour operations on an image

    :param image:
        Image to process
    :param brighten:
        Change in brightness, defaults to 1.0 for no change
    :param sharpen:
        Sharpen, defaults to None for no operation
    :param saturation:
        Saturation, defaults to None for no operation
    :return:
        The modified image
    """
    if brighten is not None and brighten is not 1.0:
        logging.info('Applying brighten {}'.format(brighten))
        image = ImageEnhance.Brightness(image).enhance(brighten)
    if sharpen is not None:
        logging.info('Applying sharpen {}'.format(sharpen))
        image = ImageEnhance.Sharpness(image).enhance(sharpen)
    if saturation is not None:
        logging.info('Applying saturation {}'.format(saturation))
        image = ImageEnhance.Color(image).enhance(saturation)
    return image

def process_image_with_border(im: Image, squares_wide: float, squares_high: float, border_north=5, border_east=5,
                              border_west=5, border_south=5, brighten=None, sharpen=None, saturation=None):
    """
    Process an image and calculate sizes, but do not split. This is used when we want to obtain a PDF of a single page
    sized exactly to the image rather than splitting an image across multiple known sized pages. Some print houses can
    accept this as an input to custom sized printing, if we're using those we don't want to split up the image or use
    a paper size larger than we need.

    :param im:
        An Image to process
    :param squares_wide:
        The number of 1 inch squares along the width of the input image
    :param squares_high:
        The number of 1 inch squares along the height of the input image
    :param border_north:
        North border (portrait orientation) in mm
    :param border_east:
        East border (portrait orientation) in mm
    :param border_south:
        South border (portrait orientation) in mm
    :param border_west:
        West border (portrait orientation) in mm
    :param brighten:
        Set to >1.0 to brighten the image before splitting, <1.0 to darken, or leave as None for no effect
    :param sharpen:
        Set to >1.0 to shapen the image before splitting.
    :param saturation:
        Set to >1.0 to enhance colour, <1.0 to remove it, None for no effect
    :return:
        Dict of image, image_width, image_height, margin_left, margin_top, page_width, page_height where all dimensions
        are specified in mm. This dict can be passed directly into process_single_image_pdf
    """
    width_pixels, height_pixels = im.size
    logging.info('process_image_with_border: Image is {} x {} pixels'.format(width_pixels, height_pixels))
    pixels_per_mm = min(width_pixels / (squares_wide * 25.4), height_pixels / (squares_high * 25.4))
    logging.info('process_image_with_border: Calculated {} pixels per mm'.format(pixels_per_mm))
    # Apply enhancements if required
    im = basic_image_ops(im, brighten, sharpen, saturation)
    image_width_mm = width_pixels / pixels_per_mm
    image_height_mm = height_pixels / pixels_per_mm

    return {
        'image': im,
        'image_width': image_width_mm,
        'image_height': image_height_mm,
        'margin_left': border_west,
        'margin_top': border_north,
        'page_width': image_width_mm + border_west + border_east,
        'page_height': image_height_mm + border_north + border_south
    }


def make_single_page_pdf(image_spec: {}, pdf_filename: str):
    """
    Take the processed image from process_image_with_border and produce a PDF file with those exact dimensions and a
    single page.

    :param image_spec:
        Return from process_image_with_border
    :param filename:
        Filename to write
    """
    pdf = FPDF(unit='mm', format=(image_spec['page_width'], image_spec['page_height']))
    with tempfile.TemporaryDirectory() as dirpath:
        pdf.add_page()
        image_spec['image'].save(f'{dirpath}/image.png')
        pdf.image(f'{dirpath}/image.png',
                  image_spec['margin_left'],
                  image_spec['margin_top'],
                  image_spec['image_width'],
                  image_spec['image_height'])
        pdf.output(pdf_filename, 'F')


def split_image(im: Image, squares_wide: float, squares_high: float, border_north=5, border_east=5, border_west=5,
                border_south=5, overlap_east=10, overlap_south=10, paper=Paper.A4, brighten=None,
                sharpen=None, saturation=None):
    """
    Split an input image into a set of images which will tile across the paper, either horizontally or vertically as
    determined by which would take the fewer pages when naively printed. At the moment this doesn't attempt to be
    clever and stack multiple small images on a single page.

    :param im:
        An Image to process
    :param squares_wide:
        The number of 1 inch squares along the width of the input image
    :param squares_high:
        The number of 1 inch squares along the height of the input image
    :param border_north:
        North border (portrait orientation) in mm
    :param border_east:
        East border (portrait orientation) in mm
    :param border_south:
        South border (portrait orientation) in mm
    :param border_west:
        West border (portrait orientation) in mm
    :param overlap_east:
        The number of mm by which the east edge (portrait) of each sheet will be extended when printing. This allows
        for easier taping of multiple pages as it's no longer so critical where the paper is cut. Defaults to 0.
    :param overlap_south:
        The number of mm by which the south edge (portrait) of each sheet will be extended when printing. This allows
        for easier taping of multiple pages as it's no longer so critical where the paper is cut. Defaults to 0.
    :param paper:
        An instance of Paper specifying the dimensions of the paper to use when tiling.
    :param brighten:
        Set to >1.0 to brighten the image before splitting, <1.0 to darken, or leave as None for no effect
    :param sharpen:
        Set to >1.0 to shapen the image before splitting.
    :param saturation:
        Set to >1.0 to enhance colour, <1.0 to remove it, None for no effect
    :return:
        A dict of {pixels_per_mm:int, images:{name : image}, orientation:str[L|P], border:int}
    """

    width_pixels, height_pixels = im.size
    logging.info('split_image: Image is {} x {} pixels'.format(width_pixels, height_pixels))
    pixels_per_mm = min(width_pixels / (squares_wide * 25.4), height_pixels / (squares_high * 25.4))
    logging.info('split_image: Calculated {} pixels per mm'.format(pixels_per_mm))

    # Apply enhancements if required
    im = basic_image_ops(im, brighten, sharpen, saturation)


    width_mm = width_pixels / pixels_per_mm
    height_mm = height_pixels / pixels_per_mm

    def get_page_size():

        printable_width = paper.width - (border_east + border_west)
        printable_height = paper.height - (border_north + border_south)

        def pages(size, printable_size, overlap):
            if math.ceil(size / printable_size) == 1:
                number_pages = 1
            else:
                number_pages = math.ceil(size / (printable_size + overlap))
            logging.debug(f'pages(size={size} printable_size={printable_size} overlap={overlap}) = {number_pages}')
            return number_pages

        pages_horizontal_p = pages(width_mm, printable_width, overlap_east)
        pages_vertical_p = pages(height_mm, printable_height, overlap_south)
        pages_horizontal_l = pages(width_mm, printable_height, overlap_south)
        pages_vertical_l = pages(height_mm, printable_width, overlap_east)

        def zero_if_one(test, value):
            if test == 1:
                return 0
            return value

        if pages_horizontal_p * pages_vertical_p > pages_horizontal_l * pages_vertical_l:
            # Use landscape orientation
            logging.info(
                'split_image: Using landscape orientation, {} by {} pages'.format(pages_horizontal_l, pages_vertical_l))
            return 'L', pages_horizontal_l, pages_vertical_l, \
                   printable_height - zero_if_one(pages_horizontal_l, overlap_south), \
                   printable_width - zero_if_one(pages_vertical_l, overlap_east)
        else:
            # Use Portrait orientation
            logging.info(
                'split_image: Using portrait orientation, {} by {} pages'.format(pages_horizontal_p, pages_vertical_p))
            return 'P', pages_horizontal_p, pages_vertical_p, \
                   printable_width - zero_if_one(pages_horizontal_p, overlap_east), \
                   printable_height - zero_if_one(pages_vertical_p, overlap_south)

    orientation, pages_horizontal, pages_vertical, page_width, page_height = get_page_size()

    pixel_width_page = page_width * pixels_per_mm
    pixel_height_page = page_height * pixels_per_mm

    if orientation == 'P':
        overlap_east_pixels = pixels_per_mm * overlap_east
        overlap_south_pixels = pixels_per_mm * overlap_south
        borders = [border_north, border_east + overlap_east, border_south + overlap_south, border_west]
    else:
        overlap_east_pixels = pixels_per_mm * overlap_south
        overlap_south_pixels = pixels_per_mm * overlap_east
        borders = [border_east, border_south + overlap_east, border_west + overlap_south, border_north]

    def crop_for(page_x, page_y):
        return im.crop((page_x * pixel_width_page, page_y * pixel_height_page,
                        min(width_pixels, (page_x + 1) * pixel_width_page + overlap_east_pixels),
                        min(height_pixels, (page_y + 1) * pixel_height_page + overlap_south_pixels)))

    return {'pixels_per_mm': pixels_per_mm,
            'images': {'{}_{}'.format(x, y): crop_for(x, y) for x in range(pages_horizontal) for y in
                       range(pages_vertical)},
            'orientation': orientation,
            'border': borders,
            'pages_horizontal': pages_horizontal,
            'pages_vertical': pages_vertical,
            'paper': paper}


def make_pdf(images, pdf_filename):
    """
    Write a set of images from split_images into a combined A4 PDF file

    :param images:
        The output dict from split_images
    :param pdf_filename:
        Full name of the PDF to write
    """
    logging.info('make_pdf: Building PDF file {} from image data'.format(pdf_filename))
    pdf = FPDF(orientation=images['orientation'], unit='mm', format=images['paper'].dimensions)
    ppm = images['pixels_per_mm']
    border_north, border_east, border_south, border_west = images['border']
    if images['orientation'] == 'P':
        page_width, page_height = images['paper'].dimensions
    else:
        page_height, page_width = images['paper'].dimensions

    def tick(x, y, size=5, gap=1, n=False, e=False, s=False, w=False, dash=False):
        line = pdf.line
        if dash:
            line = pdf.dashed_line
        if w:
            if x <= size:
                line(x - gap, y, 0, y)
            else:
                line(x - gap, y, x - size, y)
        if e:
            if page_width - x <= size:
                line(x + gap, y, page_width, y)
            else:
                line(x + gap, y, x + size, y)
        if n:
            if y <= size:
                line(x, y - gap, x, 0)
            else:
                line(x, y - gap, x, y - size)
        if s:
            if page_height - y <= size:
                line(x, y + gap, x, page_height)
            else:
                line(x, y + gap, x, y + size)

    with tempfile.TemporaryDirectory() as dirpath:
        for coords, image in images['images'].items():
            pdf.add_page()

            m = re.match(r'(\d+)_(\d+)', coords)
            x = int(m.groups()[0])
            y = int(m.groups()[1])

            im_width, im_height = image.size

            im_width_mm = im_width / ppm
            im_height_mm = im_height / ppm
            last_vertical = y == images['pages_vertical'] - 1
            last_horizontal = x == images['pages_horizontal'] - 1

            # Always position the top left one the same
            tick(border_west, border_north, n=True, w=True)
            tick(border_west, border_north + im_height_mm, s=True, w=True)
            tick(border_west + im_width_mm, border_north + im_height_mm, e=True, s=True)
            tick(border_west + im_width_mm, border_north, e=True, n=True)

            if not last_horizontal:
                tick(page_width - border_east, im_height_mm + border_north, s=True, dash=True)
                tick(page_width - border_east, border_north, n=True, dash=True)

            if not last_vertical:
                tick(border_west, page_height - border_south, w=True, dash=True)
                tick(border_west + im_width_mm, page_height - border_south, e=True, dash=True)

            # tick(page_width - border_east, border_north, n=True, e=True)
            # tick(page_width - border_east, page_height - border_south, e=True, s=True)
            image.save('{}/{}.png'.format(dirpath, coords))
            pdf.image('{}/{}.png'.format(dirpath, coords), border_west, border_north, im_width / ppm,
                      im_height / ppm)
    pdf.output(pdf_filename, 'F')
    logging.info('make_pdf: Wrote {} images to PDF file {}'.format(len(images['images']), pdf_filename))


def extract_images_from_pdf(pdf_filename: str, page=None, to_page=None, min_width=100, min_height=100,
                            min_file_size=1024 * 500):
    """
    Uses the pdfimages tool from poppler-utils to extract images from a given page of the specified PDF.

    :param pdf_filename:
        Full path of the PDF to use. Specify your pathfinder scenario PDF here.
    :param page:
        Page number to scan, None to scan all pages
    :param to_page:
        Page number up to which to scan, ignored if page is None, if left at the default this is set to whatever value
        page is set to to scan a single page, otherwise a range of pages can be specified from 'page' to 'to_page'
        inclusive
    :param min_width:
        Minimum image width to include in the output iterator, defaults to 100 pixels
    :param min_height:
        Minimum image height to include in the output iterator, defaults to 100 pixels
    :param min_file_size:
        Minimum file size to include in the output iterator, defaults to 100K
    :return:
        A lazy iterator over image objects corresponding to matching images
    """
    with tempfile.TemporaryDirectory() as dir:
        command = ['pdfimages', '-png']
        if page is not None and to_page is None:
            to_page = page
        if page is not None:
            command.extend(['-f', str(page), '-l', str(to_page)])
        command.extend([pdf_filename, dir + '/image'])
        logging.info('extract_images_from_pdf: ' + ' '.join(command))
        subprocess.run(command, shell=False, check=True, capture_output=True)
        logging.info('extract_images_from_pdf: dir={}'.format(dir))
        for entry in scandir(path=dir):
            filesize = stat(dir + '/' + entry.name).st_size
            if entry.name.endswith('png') and not entry.is_dir() and filesize >= min_file_size:
                im = Image.open(dir + '/' + entry.name)
                width, height = im.size
                if width >= min_width and height >= min_height and im.mode == 'RGB':
                    logging.info(
                        'extract_images_from_pdf: found {} - {} by {} with size {} bytes'.format(entry.name, width,
                                                                                                 height, filesize))
                    image_number = int(entry.name[entry.name.find('-') + 1:entry.name.find('.')])
                    if image_number < 99:
                        mask_name = f'image-{image_number + 1:03d}.png'
                    else:
                        mask_name = f'image-{image_number + 1}.png'
                    if isfile(dir + '/' + mask_name):
                        mask_im = Image.open(dir + '/' + mask_name)
                        mask_width, mask_height = mask_im.size
                        if mask_width == width and mask_height == height and mask_im.mode == 'L':
                            logging.info(f'Found possible mask, mode is {mask_im.mode}, '
                                         f'filename {mask_name}, combining')
                            mask_command = ['convert', dir + '/' + entry.name, dir + '/' + mask_name, '-compose',
                                            'CopyOpacity', '-composite', dir + '/' + entry.name]
                            subprocess.run(mask_command, shell=False, check=True, capture_output=True)
                            im = Image.open(dir + '/' + entry.name)
                    yield im


def run_waifu2x(image: Image, waifu2x_lua_path=None, torch_path=None, waifu2x_macos_path=None, scale=True, noise=0,
                force_cudnn=False) -> Image:
    """
    Call an existing instance of the waifu2x tool. Requires that this tool is properly installed along with torch,
    CUDA etc. Creates a temporary directory, writes the image file to it, runs waifu2x then reads back the result and
    returns it as an image object. See https://github.com/nagadomi/waifu2x for details on how to build and configure
    the tools.

    :param image:
        An image object to use as input
    :param waifu2x_lua_path:
        The full path to the waifu2x.lua file. If omitted this uses the module level WAIFU2X_LUA_PATH value
    :param torch_path:
        The full path to the 'th' executable. If omitted this uses the module level TORCH_PATH value
    :param waifu2x_macos_path:
        If set, this specifies the location of the command line macos version of waifu2x from
        https://github.com/imxieyi/waifu2x-mac/releases - this has slightly different command line usage so need to be
        handled differently
    :param scale:
        Set to True to scale by 2x, false to leave the size as is
    :param noise:
        Set to non-None to add de-noise
    :param force_cudnn:
        Set to True to force use of the cudnn library, providing a minor speed boost
    :return:
        The enhanced image
    """

    if waifu2x_lua_path is None:
        waifu2x_lua_path = WAIFU2X_LUA_PATH
    if torch_path is None:
        torch_path = TORCH_PATH

    if waifu2x_lua_path is not None:
        if not Path(waifu2x_lua_path).is_file():
            logging.info('run_waifu2x: No waifu2x lua script at {}'.format(waifu2x_lua_path))
            waifu2x_lua_path = None

    if torch_path is not None:
        if not Path(torch_path).is_file():
            logging.info('run_waifu2x: No torch executable at {}'.format(torch_path))
            torch_path = None

    if waifu2x_macos_path is None:
        waifu2x_macos_path = WAIFU2X_MACOS_PATH

    command = []

    if waifu2x_macos_path is None:

        if waifu2x_lua_path is None or torch_path is None or (scale is False and noise is None):
            # If no waifu2x specified, or nothing to do, just return the original image
            logging.info('run_waifu2x: Nothing to do, or tools unavailable, for waifu2x')
            return image

        command.extend([torch_path, waifu2x_lua_path, '-m'])

        if scale:
            if noise is None:
                command.append('scale')
            else:
                command.append('noise_scale')
        else:
            command.append('noise')

        if noise is not None:
            command.extend(['-noise_level', str(noise)])

        if force_cudnn:
            command.extend(['-force_cudnn', '1'])

    else:

        command.append(waifu2x_macos_path)

        if not Path(waifu2x_macos_path).is_file():
            logging.info('run_waifu2x: No waifu2x executable at {}'.format(waifu2x_macos_path))
            return image

        if scale:
            command.extend(['-s', '2'])
        else:
            command.extend(['-s', '1'])

        if noise is None:
            noise = 0

        command.extend(['-n', str(noise)])

    with tempfile.TemporaryDirectory() as dir:
        source = dir + '/source.png'
        dest = dir + '/dest.png'
        command.extend(['-i', source, '-o', dest])
        logging.info('run_waifu2x: Writing original image to {}'.format(source))
        image.save(source)
        logging.info('run_waifu2x: Running waifu2x: {}'.format(' '.join(command)))
        if waifu2x_lua_path is not None:
            subprocess.run(command, shell=False, check=True, cwd=dirname(waifu2x_lua_path), capture_output=True)
        else:
            subprocess.run(command, shell=False, check=True, cwd=dirname(waifu2x_macos_path), capture_output=True)
        logging.info('run_waifu2x: Completed, opening enhanced image from {}'.format(dest))
        return Image.open(dest)