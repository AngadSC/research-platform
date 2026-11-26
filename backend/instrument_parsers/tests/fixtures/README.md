# Instrument file fixtures

Small example exports copied unchanged from Benchling's `allotropy` repository
(https://github.com/Benchling-Open-Source/allotropy, MIT licence), `tests/parsers/<vendor>/testdata`.
They are test data with made-up values.

| File | Source folder |
|---|---|
| gen5_absorbance_two_wavelengths.txt | agilent_gen5/testdata/absorbance/endpoint_wavelength_measurement_labels.txt |
| gen5_kinetic.txt | agilent_gen5/testdata/absorbance/kinetic_helper_gene_growth_curve.txt |
| nanodrop_8000.txt | thermo_fisher_nanodrop_8000/testdata/Thermo_NanoDrop_8000_example01.txt |
| nanodrop_eight_rna.txt | thermo_fisher_nanodrop_eight/testdata/thermo_nanodrop_eight_RNA.txt |
| nanodrop_one_dsdna.csv | thermo_fisher_nanodrop_one/testdata/dsDNA 7_19_2023 3_27_29 PM.csv |
| qubit4.csv | thermo_fisher_qubit4/testdata/thermo_fisher_qubit4_example_1.csv |
| cfx_maestro_cq.csv | cfxmaestro/testdata/example01.csv |
| unicorn_single_uv.zip | cytiva_unicorn/testdata/unicorn_single_uv.zip |

The TIFF, FCS and AB1 files used in the tests are built in code by `instrument_parsers/tests/`.
