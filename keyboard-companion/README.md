# Keyboard Layers App Companion

This folder contains generated configuration and layer images for
`maatthc/keyboard_layers_app_companion`.

## Firmware side

This repo adds `maatthc/zmk-feature-appcompanion` in `config/west.yml`.
`config/crosses_right.conf` enables layer status reporting on the right half,
which is the Crosses split central side:

```conf
CONFIG_USB_HID_DEVICE_COUNT=2
CONFIG_ZMK_LAYER_STATUS_USB_HID=y
CONFIG_ZMK_LAYER_STATUS_BLE_HID=y
```

USB uses usage page `0xFF60` and usage `0x61`, matching `config.ini`.
BLE uses a distinct PnP identity, `0xA241:0xC054`, so the companion app can
distinguish Crosses from other ZMK boards that still use the default
`0x1D50:0x615E`.

## Regenerate assets

Run this after changing `config/crosses.keymap` and regenerating
`keymap-drawer/crosses.yaml`:

```bat
python scripts\generate-companion-assets.py
```

The script writes:

- `keyboard-companion/config.ini`
- `keyboard-companion/assets/*.png`
- `keyboard-companion/assets/*.svg`

It prefers `cairosvg` for conversion. If Cairo DLLs are unavailable on
Windows, it falls back to headless Chrome or Edge. Generated PNGs are cropped
automatically to remove extra white space around the layer.

## Run the app

1. Build and flash firmware from this repo.
2. Download or clone `https://github.com/maatthc/keyboard_layers_app_companion`.
3. Put this folder's `config.ini` at the companion app root.
4. Put this folder's `assets` files into the companion app `assets` folder.
5. Connect the keyboard over USB and run the app.

For the upstream Windows release, run:

```bat
Keyboard Companion.exe
```

From source, run:

```bat
pip install pipenv
pipenv install
pipenv run python main.py
```

Remote web display is also supported:

```bat
Keyboard Companion.exe --web
```

or from source:

```bat
pipenv run python main.py --web
```

Bluetooth mode uses the same generated images, but the upstream app must be
started with `--ble`. On macOS, Bluetooth HID access may require `sudo`.
