import pydicom, pathlib, sys

data_dir = pathlib.Path(r"F:/STAGE/DATA")
dcm_files = list(data_dir.rglob("*.dcm"))
if not dcm_files:
    print("Aucun .dcm dans", data_dir)
    sys.exit()

for path in dcm_files[:5]:
    print("=== Fichier :", path.name, "===")
    ds = pydicom.dcmread(str(path), stop_before_pixels=True)
    tags = [
        "Modality", "SOPClassUID", "Manufacturer", "ManufacturerModelName",
        "PhotometricInterpretation", "Rows", "Columns", "NumberOfFrames",
        "PixelSpacing", "ImagerPixelSpacing", "FrameTime", "FrameRate",
        "TransducerType", "BodyPartExamined", "UltrasoundColorDataPresent",
    ]
    for t in tags:
        val = getattr(ds, t, None)
        if val is not None:
            print("  " + t + ": " + str(val))
    if hasattr(ds, "SequenceOfUltrasoundRegions"):
        for i, r in enumerate(ds.SequenceOfUltrasoundRegions):
            print("  US Region [" + str(i) + "]:")
            for rt in ["PhysicalDeltaX", "PhysicalDeltaY",
                       "PhysicalUnitsXDirection", "PhysicalUnitsYDirection",
                       "RegionSpatialFormat", "RegionDataType"]:
                v = getattr(r, rt, None)
                if v is not None:
                    print("    " + rt + ": " + str(v))
    else:
        print("  (pas de SequenceOfUltrasoundRegions)")
    print()
