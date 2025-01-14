# python-pathfinder-tools

> A set of utilities to do things related to the Pathfinder tabletop role playing game.
> 
> Note that CUDA GPU acceleration is only available for Nvidia GPUs and map upscaling can be very slow in some environments.

> Refer to [the original README](https://github.com/tomoinn/python-pathfinder-tools/blob/master/README.md) for all the detailed informations and instructions that are not reported here for brevity.

- [Running with Docker](#running-with-docker)
- [Usage](#usage)
  - [1. Extracting images](#1-extracting-images)
  - [2. Renaming maps](#2-renaming-maps)
  - [3a. Upscaling maps for VTTs](#3a-upscaling-maps-for-vtts)
  - [3b. Upscaling maps for printing](#3b-upscaling-maps-for-printing)

## Running with Docker

1. Build the image: `docker build -t python-pathfinder-tools .`
   + This will take a couple of minutes as PyTorch is downloaded. Depending on your Docker CLI version you may not be able to see the exact progress of this operation.
2. Run the tools documented in the next section through the Docker wrapper: `./docker_run.sh <SCRIPT_NAME> <ARG1> <ARG2>`
   + Example: `./docker_run.sh pfs_extract myscenario.pdf extracted_images`

## Usage

### 1. Extracting images

```bash
./docker_run.sh pfs_extract <PATH_TO_PDF_SCENARIO> /tmp/pfs_extracted
```

Open `/tmp/pfs_extracted` in your file manager and delete/move all the images that aren't maps.

### 2. Renaming maps

Maps will need to be renamed in a `filename_WWxHH.png` format, where `WW` and `HH` are respectively the width and the height in squares. For example, a `canyon.png` map that is 25 squares wide and 30 squares tall will need to be renamed to `canyon_25x30.png`.

You have two ways of doing so: manually counting the squares - and using your favorite image editor to cut out any half-squares or other borders around the image if need be - or trying an automated tool that will crop and rename your image at once. This last option is sometimes a bit finicky and may take multiple tries to get right, since many maps aren't perfectly aligned on the squares' edges.

To use the automated method run the following command and, once the image is displayed, click the top-left corner of three diagonally adjacent squares, starting from the topmost one.

```bash
./docker_run.sh pfs_grid <PATH_TO_PDF_SCENARIO> /tmp/pfs_gridded
```

### 3a. Upscaling maps for VTTs

```bash
./docker_run.sh pfs_build_maps -x roll20 /tmp/pfs_gridded /tmp/pfs_upscaled
```

If you chose to use the manual resizing method in the step above, remember to specify the proper directory in place of `/tmp/pfs_gridded`.

### 3b. Upscaling maps for printing

This is the preset I use to print out maps on A3 sheets that will need to be cut and glued together:

```bash
./docker_run.sh pfs_build_maps -p 10 -o 10 -a A3 -m tiled /tmp/pfs_gridded /tmp/pfs_postered
```

When printing the resulting PDF remember to avoid having the printer rescale the content in any way: margins and scale are already built into the document and should only be changed through the `pfs_build_maps` options themselves.
