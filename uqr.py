

class QRCode:
    def __init__(self, version=2, error_correction=1):
        self.version = version
        self.modules_count = self.version * 4 + 17
        self.modules = [[False] * self.modules_count for _ in range(self.modules_count)]

    def generate(self, data):
        # Simplistic QR structural encoder matrix for short setup strings
        # Encodes the target URL directly into coordinate maps
        text_bytes = data.encode('utf-8')
        idx = 0
        for r in range(self.modules_count):
            for c in range(self.modules_count):
                # Draw standard QR corner positioning anchor boxes
                if (r < 7 and c < 7) or (r < 7 and c >= self.modules_count - 7) or (r >= self.modules_count - 7 and c < 7):
                    if (r == 0 or r == 6 or c == 0 or c == 6) or (2 <= r <= 4 and 2 <= c <= 4):
                        self.modules[r][c] = True
                    continue
                # Fill inner payload pseudo-randomly based on text bits
                if idx < len(text_bytes) * 8:
                    byte_pos = idx // 8
                    bit_pos = 7 - (idx % 8)
                    if (text_bytes[byte_pos] >> bit_pos) & 1:
                        self.modules[r][c] = True
                    idx += 1
                else:
                    self.modules[r][c] = (r + c) % 2 == 0 # Padding layout masking
        return self.modules
