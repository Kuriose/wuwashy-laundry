"""Pembuat file Excel (.xlsx) tanpa pustaka tambahan: cukup modul bawaan Python (zipfile + XML).

File .xlsx adalah arsip ZIP berisi beberapa berkas XML. Modul ini menulis versi yang paling sederhana dan
dibuka normal di Microsoft Excel, LibreOffice, dan Google Sheets.

OOP - Enkapsulasi: urusan format OOXML (nama berkas, XML, nomor gaya) dibungkus di kelas BukuKerja dan Lembar.
Pemanggil cukup menyusun baris data lalu memanggil `BukuKerja.simpan()`.
OOP - Abstraksi: pemanggil memilih gaya lewat nama (Gaya.HEADER, Gaya.RUPIAH, ...), bukan nomor gaya XML.
"""
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

_ILEGAL = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')  # karakter kontrol yang membuat XML/Excel rusak
_EPOCH = datetime(1899, 12, 30)


class Gaya:
    """Nama gaya sel. Nilainya adalah nomor `cellXfs` di styles.xml (lihat _STYLES)."""
    BIASA, JUDUL, KETERANGAN, HEADER, ANGKA, RUPIAH, PERSEN, TANGGAL, WAKTU, TEBAL, TOTAL_ANGKA, TOTAL_RUPIAH, DESIMAL = range(13)


_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="4">
<numFmt numFmtId="164" formatCode="&quot;Rp&quot;\\ #,##0"/>
<numFmt numFmtId="165" formatCode="dd/mm/yyyy"/>
<numFmt numFmtId="166" formatCode="dd/mm/yyyy\\ hh:mm"/>
<numFmt numFmtId="167" formatCode="#,##0.0"/>
</numFmts>
<fonts count="5">
<font><sz val="11"/><color rgb="FF0B1230"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="15"/><color rgb="FF0B1230"/><name val="Calibri"/><family val="2"/></font>
<font><i/><sz val="10"/><color rgb="FF6B7691"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><color rgb="FF0B1230"/><name val="Calibri"/><family val="2"/></font>
</fonts>
<fills count="4">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF0B1230"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEEF3FB"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top style="thin"><color rgb="FFC9D2E3"/></top><bottom style="thin"><color rgb="FFC9D2E3"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="13">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="left"/></xf>
<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="left"/></xf>
<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="3" fontId="4" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="164" fontId="4" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


class Sel:
    """Satu sel dengan gaya khusus. Sel biasa cukup ditulis sebagai nilai polos (str, angka, tanggal)."""

    def __init__(self, nilai, gaya=Gaya.BIASA):
        self.nilai, self.gaya = nilai, gaya


def _nama_kolom(i):
    """0 -> A, 25 -> Z, 26 -> AA."""
    nama = ''
    i += 1
    while i:
        i, sisa = divmod(i - 1, 26)
        nama = chr(65 + sisa) + nama
    return nama


def _serial_excel(nilai):
    """date / datetime -> nomor seri tanggal Excel (hari sejak 30 Des 1899)."""
    if isinstance(nilai, datetime):
        if nilai.tzinfo is not None:
            nilai = nilai.replace(tzinfo=None)  # waktu sudah diubah ke zona lokal oleh pemanggil
        selisih = nilai - _EPOCH
        return selisih.days + selisih.seconds / 86400
    return (datetime(nilai.year, nilai.month, nilai.day) - _EPOCH).days


class Lembar:
    """Satu sheet. Baris ditambahkan berurutan dengan tambah()."""

    NAMA_ILEGAL = re.compile(r'[\\/*?:\[\]]')

    def __init__(self, nama):
        nama = self.NAMA_ILEGAL.sub(' ', nama).strip() or 'Sheet'
        self.nama = nama[:31]  # batas Excel
        self._baris = []  # list of list[Sel]
        self._lebar = []
        self._beku = None
        self._filter = None

    @property
    def jumlah_baris(self):
        return len(self._baris)

    def tambah(self, sel=(), gaya=Gaya.BIASA):
        """Tambah satu baris. `gaya` berlaku untuk sel polos; sel bertipe Sel membawa gayanya sendiri."""
        self._baris.append([s if isinstance(s, Sel) else Sel(s, gaya) for s in sel])
        return self

    def kosong(self, jumlah=1):
        for _ in range(jumlah):
            self._baris.append([])
        return self

    def lebar_kolom(self, *lebar):
        self._lebar = list(lebar)
        return self

    def bekukan(self, baris, kolom=0):
        """Bekukan `baris` baris teratas (dan `kolom` kolom kiri) supaya tetap terlihat saat menggulir."""
        self._beku = (baris, kolom)
        return self

    def filter_otomatis(self, baris_header, jumlah_kolom, baris_akhir):
        """Tombol filter di baris header (nomor baris mulai dari 1)."""
        self._filter = f'A{baris_header}:{_nama_kolom(jumlah_kolom - 1)}{baris_akhir}'
        return self

    # ---------- XML ----------
    def _xml_sel(self, ref, s):
        v, g = s.nilai, s.gaya
        if v is None or v == '':
            return f'<c r="{ref}" s="{g}"/>' if g else ''
        if isinstance(v, bool):
            return f'<c r="{ref}" s="{g}" t="b"><v>{int(v)}</v></c>'
        if isinstance(v, (datetime, date)):
            if g == Gaya.BIASA:
                g = Gaya.WAKTU if isinstance(v, datetime) else Gaya.TANGGAL
            return f'<c r="{ref}" s="{g}"><v>{_serial_excel(v)!r}</v></c>'
        if isinstance(v, (int, float, Decimal)):
            return f'<c r="{ref}" s="{g}"><v>{v}</v></c>'
        teks = escape(_ILEGAL.sub('', str(v)))
        return f'<c r="{ref}" s="{g}" t="inlineStr"><is><t xml:space="preserve">{teks}</t></is></c>'

    def xml(self):
        bagian = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        if self._beku:
            baris, kolom = self._beku
            sel_kiri = f'{_nama_kolom(kolom)}{baris + 1}'
            atribut = ''
            if kolom:
                atribut += f' xSplit="{kolom}"'
            if baris:
                atribut += f' ySplit="{baris}"'
            panel = 'bottomRight' if kolom and baris else ('bottomLeft' if baris else 'topRight')
            bagian.append(f'<sheetViews><sheetView workbookViewId="0"><pane{atribut} topLeftCell="{sel_kiri}" '
                          f'activePane="{panel}" state="frozen"/></sheetView></sheetViews>')
        if self._lebar:
            kolom = ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(self._lebar, 1))
            bagian.append(f'<cols>{kolom}</cols>')
        bagian.append('<sheetData>')
        for n, baris in enumerate(self._baris, 1):
            sel = ''.join(self._xml_sel(f'{_nama_kolom(i)}{n}', s) for i, s in enumerate(baris))
            tinggi = ' ht="22" customHeight="1"' if any(s.gaya == Gaya.JUDUL for s in baris) else ''
            bagian.append(f'<row r="{n}"{tinggi}>{sel}</row>' if sel else f'<row r="{n}"/>')
        bagian.append('</sheetData>')
        if self._filter:
            bagian.append(f'<autoFilter ref="{self._filter}"/>')
        bagian.append('<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>')
        bagian.append('</worksheet>')
        return ''.join(bagian)


class BukuKerja:
    """Satu berkas .xlsx berisi satu atau lebih Lembar."""

    def __init__(self):
        self._lembar = []

    def lembar(self, nama):
        l = Lembar(nama)
        if any(x.nama.lower() == l.nama.lower() for x in self._lembar):
            raise ValueError(f'Nama sheet ganda: {l.nama}')
        self._lembar.append(l)
        return l

    def simpan(self):
        """Hasilkan isi berkas .xlsx sebagai bytes."""
        if not self._lembar:
            raise ValueError('Buku kerja kosong: tambahkan minimal satu lembar.')
        n = len(self._lembar)
        tipe = ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, n + 1))
        sheets = ''.join(f'<sheet name="{escape(l.nama, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>' for i, l in enumerate(self._lembar, 1))
        rel = ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
        rel += f'<Relationship Id="rId{n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        berkas = {
            '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + tipe + '</Types>',
            '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
            'xl/workbook.xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + sheets + '</sheets></workbook>',
            'xl/_rels/workbook.xml.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + rel + '</Relationships>',
            'xl/styles.xml': _STYLES,
        }
        for i, l in enumerate(self._lembar, 1):
            berkas[f'xl/worksheets/sheet{i}.xml'] = l.xml()
        keluaran = io.BytesIO()
        with zipfile.ZipFile(keluaran, 'w', zipfile.ZIP_DEFLATED) as z:
            for nama, isi in berkas.items():
                z.writestr(nama, isi)
        return keluaran.getvalue()
