# CrowPanel E-paper display library, based on SSD1683 chip
# Supported screens:
#   CrowPanel 5.79" (dual SSD1683 chip)
#   CrowPanel 4.20" (single SSD1683 chip, not tested - please report)
#
# Built on top of MicroPython framebuf.FrameBuffer.
#
# V0.1.0 Dec 2024 Initial version
# V0.1.1 Jan 2025 Fixed initialization of screen
# V0.1.2 Jan 2025 Added buffer area inversion
# V0.1.3 May 2026 Added FromFrameBuffer function
# V0.1.4 May 2026 Tried to fix 4.20" initialization (NOT tested) for mirrored view. Please report
# V0.1.5 May 2026 Added SD Card support
# V0.1.6 May 2026 Fixed FAST update reverting to FULL waveform after SCREEN_UPDATE_FULL call
#
# Released under the MIT License (MIT).
# Copyright (c) 2025 Ignas Bukys
from micropython import const
from time import sleep_ms
import framebuf
from ustruct import pack
from io import BytesIO
from machine import SPI, Pin, SDCard

__version__ = (0, 1, 6)

# Display colour codes
COLOR_WHITE = const(1)
COLOR_BLACK = const(0)

SCREEN_UPDATE_FAST = const(1)
SCREEN_UPDATE_PART = const(2)
SCREEN_UPDATE_FULL = const(0)


class SSD1683(framebuf.FrameBuffer):
    '''Base class for SSD1683 e-paper controller. Provides SPI communication,
    frame buffer management, and display update primitives.
    Not intended to be used directly — use Screen_579 or Screen_420 instead.
    '''

    # SSD1683 command register addresses
    SET_DRIVER_CONTROL      = const(0x01)
    SET_GATE_VOLTAGE        = const(0x03)
    SET_SOURCE_VOLTAGE      = const(0x04)
    SET_DISPLAY_CONTROL     = const(0x07)
    SET_NON_OVERLAP         = const(0x0B)
    SET_BOOSTER_SOFT_START  = const(0x0C)
    SET_GATE_SCAN_START     = const(0x0F)
    SET_DEEP_SLEEP          = const(0x10)
    SET_DATA_MODE           = const(0x11)
    SET_DATA_MODE_SLAVE     = const(0x91)
    SET_SW_RESET            = const(0x12)
    SET_TEMP_WRITE          = const(0x1A)
    SET_TEMP_READ           = const(0x1B)
    SET_TEMP_CONTROL        = const(0x18)
    SET_TEMP_LOAD           = const(0x1A)
    SET_MASTER_ACTIVATE     = const(0x20)
    SET_DISP_CTRL1          = const(0x21)
    SET_DISP_CTRL2          = const(0x22)
    SET_WRITE_RAM           = const(0x24)
    SET_WRITE_ALTRAM        = const(0x26)
    SET_READ_RAM            = const(0x25)
    SET_VCOM_SENSE          = const(0x2B)
    SET_VCOM_DURATION       = const(0x2C)
    SET_WRITE_VCOM          = const(0x2C)
    SET_READ_OTP            = const(0x2D)
    SET_WRITE_LUT           = const(0x32)
    SET_WRITE_DUMMY         = const(0x3A)
    SET_WRITE_GATELINE      = const(0x3B)
    SET_WRITE_BORDER        = const(0x3C)
    SET_RAMXPOS             = const(0x44)
    SET_RAMYPOS             = const(0x45)
    SET_RAMXCOUNT           = const(0x4E)
    SET_RAMYCOUNT           = const(0x4F)
    SET_WRITE_RAM_SLAVE     = const(0xA4)
    SET_WRITE_ALTRAM_SLAVE  = const(0xA6)
    SET_RAMXPOS_SLAVE       = const(0xC4)
    SET_RAMYPOS_SLAVE       = const(0xC5)
    SET_RAMXCOUNT_SLAVE     = const(0xCE)
    SET_RAMYCOUNT_SLAVE     = const(0xCF)
    SET_NOP                 = const(0xFF)

    # GPIO pin assignments
    LED_PIN     = const(41)
    RESET_PIN   = const(47)
    BUSY_PIN    = const(48)
    DC_PIN      = const(46)
    MOSI_PIN    = const(11)
    SCK_PIN     = const(12)
    CS_PIN      = const(45)
    SCREEN_PWR  = const(7)

    # Rotation constants
    ROTATION_0   = const(0)
    ROTATION_90  = const(1)
    ROTATION_180 = const(2)
    ROTATION_270 = const(3)

    def __init__(self, w: int, h: int, rotation: int = ROTATION_0, auto_sync_alt_ram: bool = True) -> None:
        '''Initialise the SSD1683 controller.

        Parameters
        ----------
        w : int
            Screen width in pixels.
        h : int
            Screen height in pixels.
        rotation : int, optional
            One of ROTATION_0/90/180/270. Default ROTATION_0.
        auto_sync_alt_ram : bool, optional
            When True (default), the fast-refresh waveform LUT and alt-RAM are
            automatically restored after every SCREEN_UPDATE_FULL call, so the
            next SCREEN_UPDATE_FAST works correctly without any extra steps.
            Set to False if you want full control and will call FastMode1Init()
            and sync_alt_ram() yourself.
        '''
        self.auto_sync_alt_ram = auto_sync_alt_ram
        self._init_spi()
        self._init_buffer(w, h, rotation)
        self.FastMode1Init()
        self.HW_RESET()

    def _init_spi(self) -> None:
        Pin(self.SCREEN_PWR, Pin.OUT, value=1)  # enable screen power rail

        self.cs   = Pin(self.CS_PIN,    Pin.OUT)
        self.dc   = Pin(self.DC_PIN,    Pin.OUT)
        self.rst  = Pin(self.RESET_PIN, Pin.OUT)
        self.busy = Pin(self.BUSY_PIN,  Pin.IN)

        self.spi = SPI(1,
            baudrate=4_000_000,
            sck=Pin(self.SCK_PIN),
            mosi=Pin(self.MOSI_PIN),
            polarity=0,
            phase=0,
            firstbit=SPI.MSB)

        self.spi.init()
        self.cs.init(self.cs.OUT,   value=1)
        self.dc.init(self.dc.OUT,   value=1)
        self.rst.init(self.rst.OUT, value=1)
        self.busy.init(self.busy.IN, value=0)

    def _init_buffer(self, w: int, h: int, rotation: int) -> None:
        self._rotation = rotation
        size = w * h // 8
        self.buffer = bytearray(size)
        self.width  = w
        self.height = h
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_HLSB)
        print('Buffer width:{}, height:{}, size:{}'.format(self.width, self.height, size))

    def _cmd(self, command: int, data: int | None = None) -> None:
        '''Send a command byte, with an optional single data byte.'''
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([command]))
        self.cs(1)
        if data is not None:
            self._data(data)

    def _data(self, data: int) -> None:
        '''Send a single data byte.'''
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(bytearray([data]))
        self.cs(1)

    def _data_s(self, data: bytes | bytearray) -> None:
        '''Send a stream of data bytes.'''
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(pack('B' * len(data), *data))
        self.cs(1)

    def _wait_until_idle(self) -> None:
        while self.busy.value() == 1:
            sleep_ms(10)

    def HW_RESET(self) -> None:
        '''Perform a hardware reset via the RST pin.'''
        sleep_ms(10)
        self.rst(0)
        sleep_ms(10)
        self.rst(1)
        sleep_ms(10)
        self._wait_until_idle()

    def EPD_Init(self) -> None:
        '''Hard reset followed by software reset. Leaves the controller ready
        to receive RAM data and display commands.'''
        self.HW_RESET()
        self._wait_until_idle()
        self._cmd(self.SET_SW_RESET)
        self._wait_until_idle()

    def FastMode1Init(self) -> None:
        '''Load the fast-refresh waveform LUT from the built-in temperature
        sensor. Must be called once at startup and again after any
        SCREEN_UPDATE_FULL, because 0xF7 (full waveform) overwrites the
        active LUT and subsequent FastUpdate() calls would use the wrong one.
        '''
        self.EPD_Init()
        self._cmd(self.SET_TEMP_CONTROL, 0x80)  # use built-in temperature sensor
        self._cmd(self.SET_DISP_CTRL2, 0xB1)    # load temperature reading
        self._cmd(self.SET_MASTER_ACTIVATE)
        self._wait_until_idle()
        self._cmd(self.SET_TEMP_WRITE, 0x64)    # write temperature register
        self._data(0x00)
        self._cmd(self.SET_DISP_CTRL2, 0x91)    # load fast waveform LUT for this temperature
        self._cmd(self.SET_MASTER_ACTIVATE)
        self._wait_until_idle()
        self._cmd(self.SET_WRITE_BORDER, 0x1)
        self._wait_until_idle()

    def Update(self) -> None:
        '''Trigger a full waveform display update (slowest, clearest).'''
        self._cmd(self.SET_DISP_CTRL2, 0xF7)
        self._cmd(self.SET_MASTER_ACTIVATE)
        self._wait_until_idle()

    def PartUpdate(self) -> None:
        '''Trigger a partial display update.'''
        self._cmd(self.SET_DISP_CTRL2, 0xDC)
        self._cmd(self.SET_MASTER_ACTIVATE)
        self._wait_until_idle()

    def FastUpdate(self) -> None:
        '''Trigger a fast display update (fewest blinks, requires fast LUT loaded).'''
        self._cmd(self.SET_DISP_CTRL2, 0xC7)
        self._cmd(self.SET_MASTER_ACTIVATE)
        self._wait_until_idle()

    def DeepSleep(self, mode: int = 0x01) -> None:
        '''Put the controller into deep sleep to save power.
        Call EPD_Init() to wake up.

        Parameters
        ----------
        mode : int, optional
            0x00 - Normal
            0x01 - Mode 1 (default)
            0x11 - Mode 2, no RAM retention
        '''
        self._cmd(self.SET_DEEP_SLEEP, mode)
        sleep_ms(5)

    def FromFrameBuffer(self, fb: framebuf.FrameBuffer, PosX: int, PosY: int, blitkey: int = -1) -> None:
        '''Blit an external FrameBuffer object into the screen buffer.

        Parameters
        ----------
        fb : framebuf.FrameBuffer
            Source frame buffer.
        PosX, PosY : int
            Top-left destination coordinates.
        blitkey : int, optional
            Transparent colour key. -1 disables transparency.
        '''
        self.blit(fb, PosX, PosY, blitkey)

    def LoadImage(self, PosX: int, PosY: int, ImgName: str, ImgWidth: int, ImgHeight: int, blitkey: int = -1) -> None:
        '''Load a raw 1-bit image file into the screen buffer.

        The image must be black-and-white, exported as
        "Horizontal - 1 bit per pixel" (framebuf.MONO_HLSB) using
        https://javl.github.io/image2cpp/

        Parameters
        ----------
        PosX, PosY : int
            Top-left destination coordinates.
        ImgName : str
            Path to the raw .bin image file.
        ImgWidth, ImgHeight : int
            Image dimensions in pixels.
        blitkey : int, optional
            Transparent colour key. -1 disables transparency.
        '''
        img_data = bytearray(ImgWidth * ImgHeight // 8)
        with open(ImgName, 'rb') as f:
            f.readinto(img_data)
        img_buf = framebuf.FrameBuffer(img_data, ImgWidth, ImgHeight, framebuf.MONO_HLSB)
        self.blit(img_buf, PosX, PosY, blitkey)

    def InvertArea(self, x: int, y: int, width: int, height: int) -> None:
        '''Invert all pixel colours within a rectangular region of the buffer.

        Parameters
        ----------
        x, y : int
            Top-left corner of the region.
        width, height : int
            Size of the region in pixels.

        Raises
        ------
        ValueError
            If the region extends outside the buffer bounds.
        '''
        byte_offset = (y * self.width + x) // 8
        for row in range(height):
            for col in range(width):
                byte_index = byte_offset + (row * self.width + col) // 8
                bit_index  = (row * self.width + col) % 8
                if byte_index >= len(self.buffer):
                    raise ValueError("Area exceeds buffer bounds.")
                self.buffer[byte_index] ^= (1 << bit_index)


class Screen_579(SSD1683):
    '''CrowPanel 5.79" e-paper display (dual SSD1683 chip).'''

    EPD_WIDTH  = 792
    EPD_HEIGHT = 272

    def __init__(self, auto_sync_alt_ram: bool = True) -> None:
        '''
        Parameters
        ----------
        auto_sync_alt_ram : bool, optional
            See SSD1683.__init__ for full description. Default True.
        '''
        super().__init__(self.EPD_WIDTH, self.EPD_HEIGHT, auto_sync_alt_ram=auto_sync_alt_ram)
        self.Prepare()

    def Prepare(self) -> None:
        '''Fill RAM and alt-RAM of both chips with known initial values.
        Called once at startup to establish a clean baseline for fast updates.
        '''
        count = (self.EPD_WIDTH + 8) * self.EPD_HEIGHT // 8
        self.SetRAMMP()
        self.SetRAMMA()
        self._cmd(self.SET_WRITE_RAM)
        self._data_s(b'\xFF' * count)
        self.SetRAMMA()
        self._cmd(self.SET_WRITE_ALTRAM)
        self._data_s(b'\x00' * count)
        self.SetRAMSP()
        self.SetRAMSA()
        self._cmd(self.SET_WRITE_RAM_SLAVE)
        self._data_s(b'\xFF' * count)
        self.SetRAMSA()
        self._cmd(self.SET_WRITE_ALTRAM_SLAVE)
        self._data_s(b'\x00' * count)

    def SetRAMMP(self) -> None:
        '''Set data entry mode and address window for primary chip RAM.'''
        self._cmd(self.SET_DATA_MODE, 0x02)
        self._cmd(self.SET_RAMXPOS)
        self._data(0x31)
        self._data(0x00)
        self._cmd(self.SET_RAMYPOS)
        self._data(0x00)
        self._data(0x00)
        self._data(0x0f)
        self._data(0x01)

    def SetRAMMA(self) -> None:
        '''Reset address counter for primary chip alt-RAM.'''
        self._cmd(self.SET_RAMXCOUNT, 0x31)
        self._cmd(self.SET_RAMYCOUNT, 0x00)
        self._data(0x00)

    def SetRAMSP(self) -> None:
        '''Set data entry mode and address window for slave chip RAM.'''
        self._cmd(self.SET_DATA_MODE_SLAVE, 0x03)
        self._cmd(self.SET_RAMXPOS_SLAVE)
        self._data(0x00)
        self._data(0x31)
        self._cmd(self.SET_RAMYPOS_SLAVE)
        self._data(0x00)
        self._data(0x00)
        self._data(0x0f)
        self._data(0x01)

    def SetRAMSA(self) -> None:
        '''Reset address counter for slave chip alt-RAM.'''
        self._cmd(self.SET_RAMXCOUNT_SLAVE, 0x00)
        self._cmd(self.SET_RAMYCOUNT_SLAVE, 0x00)
        self._data(0x00)

    def sync_alt_ram(self) -> None:
        '''Copy the current frame buffer into alt-RAM on both chips.

        Normally called automatically by show() after SCREEN_UPDATE_FULL
        when auto_sync_alt_ram=True. Only call this manually if you
        initialised with auto_sync_alt_ram=False.

        Alt-RAM holds the previous frame that the chip diffs against during
        a fast update. SCREEN_UPDATE_FULL does not update alt-RAM, so without
        this sync the next SCREEN_UPDATE_FAST would diff against stale content
        and silently execute a full waveform instead (3 blinks).

        The buffer is written using the same interleaved chunk pattern as
        show(), so each chip's alt-RAM receives exactly the same bytes as
        its RAM — making the diff zero and the fast update a true no-change
        baseline.
        '''
        # Reset address window on both chips before writing
        self.SetRAMMP()
        self.SetRAMSP()

        # Mirror the interleaved write pattern from show():
        # slave gets bytes 0..49, primary gets 49..98, slave gets 98..147 ...
        # with a 1-byte overlap at each chunk boundary to handle the pixel
        # that sits on the border between the two physical chips.
        bitmap_buffer = BytesIO(self.buffer) # type: ignore
        while True:
            chunk = bitmap_buffer.read(50)
            if not chunk: break
            self.SetRAMSA()
            self._cmd(self.SET_WRITE_ALTRAM_SLAVE)
            self._data_s(chunk)
            bitmap_buffer.seek(-1, 1)
            chunk = bitmap_buffer.read(50)
            if not chunk: break
            self.SetRAMMA()
            self._cmd(self.SET_WRITE_ALTRAM)
            self._data_s(chunk)
        bitmap_buffer.close()

    def show(self, mode: int = SCREEN_UPDATE_FAST) -> None:
        '''Flush the frame buffer to the display.

        Parameters
        ----------
        mode : int, optional
            SCREEN_UPDATE_FAST (1) - fast, minimal flicker. Default.
            SCREEN_UPDATE_PART (2) - partial update.
            SCREEN_UPDATE_FULL (0) - full waveform, slowest but clearest.

        Raises
        ------
        ValueError
            If the frame buffer size does not match the screen resolution.
        '''
        if len(self.buffer) != self.EPD_WIDTH * self.EPD_HEIGHT // 8:
            raise ValueError("Invalid frame buffer size. Expected {} bytes.".format(
                self.EPD_WIDTH * self.EPD_HEIGHT // 8))

        # The 5.79" screen uses two SSD1683 chips side by side. The buffer is
        # written in interleaved 50-byte chunks with a 1-byte overlap at each
        # boundary to share the pixel that falls between the two chips.
        bitmap_buffer = BytesIO(self.buffer) # type:ignore
        while True:
            chunk = bitmap_buffer.read(50)
            if not chunk: break
            self._cmd(self.SET_WRITE_RAM_SLAVE)
            self._data_s(chunk)
            bitmap_buffer.seek(-1, 1)
            chunk = bitmap_buffer.read(50)
            if not chunk: break
            self._cmd(self.SET_WRITE_RAM)
            self._data_s(chunk)
        bitmap_buffer.close()

        if mode == SCREEN_UPDATE_FAST:
            self.FastUpdate()
        elif mode == SCREEN_UPDATE_PART:
            self.PartUpdate()
        else:
            self.Update()
            if self.auto_sync_alt_ram:
                # 0xF7 (full waveform) overwrites the active LUT in the controller.
                # FastMode1Init() reloads the fast LUT so the next FastUpdate()
                # works correctly. sync_alt_ram() then aligns alt-RAM with the
                # frame just displayed, so the fast-update diff starts clean.
                self.FastMode1Init()
                self.sync_alt_ram()


class Screen_420(SSD1683):
    '''CrowPanel 4.20" e-paper display (single SSD1683 chip).
    Note: not tested — please report any issues.
    '''

    EPD_HEIGHT = 300
    EPD_WIDTH  = 400

    def __init__(self, auto_sync_alt_ram: bool = True) -> None:
        '''
        Parameters
        ----------
        auto_sync_alt_ram : bool, optional
            See SSD1683.__init__ for full description. Default True.
        '''
        super().__init__(self.EPD_WIDTH, self.EPD_HEIGHT, auto_sync_alt_ram=auto_sync_alt_ram)
        self.Prepare()

    def Prepare(self) -> None:
        '''Fill RAM and alt-RAM with known initial values.
        Called once at startup to establish a clean baseline for fast updates.
        '''
        count = self.EPD_WIDTH * self.EPD_HEIGHT // 8
        self.SetRAMMP()
        self.SetRAMMA()
        self._cmd(self.SET_WRITE_RAM)
        self._data_s(b'\xFF' * count)
        self.SetRAMMA()
        self._cmd(self.SET_WRITE_ALTRAM)
        self._data_s(b'\x00' * count)

    def SetRAMMP(self) -> None:
        '''Set data entry mode and address window for RAM.'''
        self._cmd(self.SET_DATA_MODE, 0x03)
        self._cmd(self.SET_RAMXPOS)
        self._data(0x00)
        self._data(0x49)
        self._cmd(self.SET_RAMYPOS)
        self._data(0x00)
        self._data(0x00)
        self._data(0x43)
        self._data(0x01)

    def SetRAMMA(self) -> None:
        '''Reset address counter for alt-RAM.'''
        self._cmd(self.SET_RAMXCOUNT, 0x00)
        self._cmd(self.SET_RAMYCOUNT, 0x00)
        self._data(0x00)

    def sync_alt_ram(self) -> None:
        '''Copy the current frame buffer into alt-RAM.

        Normally called automatically by show() after SCREEN_UPDATE_FULL
        when auto_sync_alt_ram=True. Only call this manually if you
        initialised with auto_sync_alt_ram=False.
        '''
        self.SetRAMMP()
        self.SetRAMMA()
        self._cmd(self.SET_WRITE_ALTRAM)
        self._data_s(self.buffer)

    def show(self, mode: int = SCREEN_UPDATE_FAST) -> None:
        '''Flush the frame buffer to the display.

        Parameters
        ----------
        mode : int, optional
            SCREEN_UPDATE_FAST (1) - fast, minimal flicker. Default.
            SCREEN_UPDATE_PART (2) - partial update.
            SCREEN_UPDATE_FULL (0) - full waveform, slowest but clearest.

        Raises
        ------
        ValueError
            If the frame buffer size does not match the screen resolution.
        '''
        if len(self.buffer) != self.EPD_WIDTH * self.EPD_HEIGHT / 8:
            raise ValueError("Invalid frame buffer size. Expected {} bytes.".format(
                self.EPD_WIDTH * self.EPD_HEIGHT // 8))

        self._cmd(self.SET_WRITE_RAM)
        self._data_s(self.buffer)

        if mode == SCREEN_UPDATE_FAST:
            self.FastUpdate()
        elif mode == SCREEN_UPDATE_PART:
            self.PartUpdate()
        else:
            self.Update()
            if self.auto_sync_alt_ram:
                # Same reasoning as Screen_579: reload fast LUT then sync alt-RAM.
                self.FastMode1Init()
                self.sync_alt_ram()


class SD_Card():
    '''Mount the SD card on /sd.

    Usage: SD_Card()
    '''
    def __init__(self) -> None:
        SDCARD_SLOT = const(2)
        SDCARD_PWR  = const(42)
        SDCARD_CS   = const(10)
        SDCARD_MOSI = const(40)
        SDCARD_CLK  = const(39)
        SDCARD_MISO = const(13)
        import vfs
        Pin(SDCARD_PWR, Pin.OUT, value=1)
        sd = SDCard(slot=SDCARD_SLOT,
                    sck=SDCARD_CLK,
                    miso=SDCARD_MISO,
                    mosi=SDCARD_MOSI,
                    cs=SDCARD_CS)
        vfs.mount(sd, "/sd")
        print("SD card mounted on '/sd'")
