"""Rebuild the clearly labeled synthetic CSV fixture; no account export is simulated."""
import csv
from pathlib import Path

ROWS = [
    ("Roofing", "Roof coverings", "Roof covering material", '<p>The roof covering is <strong>asphalt composition shingle</strong>.</p>', "info"),
    ("Roofing", "Roof coverings", "Localized shingle wear", '<p>Localized wear was observed at the shingles. Have a qualified roofing contractor evaluate and repair as needed.</p>', "defect"),
    ("Roofing", "Roof coverings", "Roof inspection method", '<p>The roof was observed from accessible ground-level vantage points. Concealed conditions were not evaluated.</p>', "limit"),
    ("Roofing", "Flashing & penetrations", "Roof penetration flashing", '<p>Flashing was observed at accessible roof penetrations.</p><ul><li>Vent stacks</li><li>Roof-to-wall transitions</li></ul>', "info"),
    ("Roofing", "Flashing & penetrations", "Sealant deterioration", '<p>Sealant is deteriorated at a roof penetration. Recommend evaluation by a qualified roofing contractor.</p>', "defect"),
    ("Roofing", "Gutters & drainage", "Roof drainage", '<p>Gutters and downspouts are installed along accessible eaves.</p>', "info"),
    ("Roofing", "Gutters & drainage", "Debris in gutters", '<p>Debris is present in the gutters. Clean the gutters and verify drainage.</p>', "defect"),
    ("Exterior", "Wall cladding", "Exterior wall finish", '<p>Exterior wall finishes include <em>brick veneer</em> and fiber cement siding.</p>', "info"),
    ("Exterior", "Wall cladding", "Cladding clearance", '<p>Cladding is close to the soil at the noted area. Consult a qualified contractor about appropriate clearance.</p>', "defect"),
    ("Exterior", "Doors & windows", "Accessible exterior doors", '<p>Accessible exterior doors were operated during the inspection.</p>', "info"),
    ("Exterior", "Doors & windows", "Sealant maintenance", '<p>Open sealant joints were observed at window trim. Repair to reduce water entry.</p>', "defect"),
    ("Exterior", "Grading & drainage", "Site drainage", '<p>The visible grade generally slopes away from the foundation.</p>', "info"),
    ("Structure", "Foundation", "Visible foundation", '<p>The visible foundation is poured concrete. Interior finishes limit visibility.</p>', "info"),
    ("Structure", "Foundation", "Stored belongings", '<p>Stored belongings restricted access to portions of the foundation.</p>', "limit"),
    ("Structure", "Framing", "Accessible framing", '<p>Accessible framing was visually inspected. Concealed connections were not evaluated.</p>', "info"),
    ("Electrical", "Service equipment", "Service equipment location", '<p>The electrical service equipment is located at the exterior utility wall.</p>', "info"),
    ("Electrical", "Service equipment", "Panel access", '<p>Maintain clear and unobstructed access to electrical equipment.</p>', "info"),
    ("Electrical", "Receptacles", "Loose receptacle", '<p>A receptacle is loose at the indicated location. Have a qualified electrician secure and evaluate it.</p>', "defect"),
    ("Electrical", "Receptacles", "Representative sample", '<p>A representative sample of accessible receptacles was tested. Furniture restricted access to others.</p>', "limit"),
    ("Heating & cooling", "Heating equipment", "Heating system", '<p>The heating equipment is a forced-air furnace. The equipment responded to normal operating controls.</p>', "info"),
    ("Heating & cooling", "Heating equipment", "Service history", '<p>Obtain available service records and follow the manufacturer’s maintenance schedule.</p>', "info"),
    ("Heating & cooling", "Cooling equipment", "Outdoor temperature limitation", '<p>The cooling system was not operated because outdoor conditions were outside the manufacturer’s operating range.</p>', "limit"),
    ("Heating & cooling", "Distribution", "Air filter", '<p>The air filter is dirty. Replace it with the size and type specified for this equipment.</p>', "defect"),
    ("Plumbing", "Water supply", "Visible supply piping", '<p>Accessible water supply piping was observed. Concealed piping was not evaluated.</p>', "info"),
    ("Plumbing", "Fixtures", "Sink drainage", '<p>The accessible sink drained when operated. Flow was observed under normal use.</p>', "info"),
    ("Plumbing", "Fixtures", "Slow drainage", '<p>Drainage was slow at the noted fixture. Recommend evaluation and correction by a qualified plumber.</p>', "defect"),
    ("Plumbing", "Water heating", "Water heater", '<p>The water heater is located in the utility area. See the equipment label for capacity and manufacturer information.</p>', "info"),
    ("Interior", "Walls & ceilings", "Interior finishes", '<p>Interior wall and ceiling finishes were observed in accessible areas.</p>', "info"),
    ("Interior", "Walls & ceilings", "Localized staining", '<p>Localized staining was observed. Identify the source and repair as appropriate; concealed conditions were not determined.</p>', "defect"),
    ("Interior", "Doors", "Interior door operation", '<p>Accessible interior doors were operated. One door rubs at its frame.</p>', "defect"),
    ("Attic & insulation", "Access", "Attic access", '<p>The attic was observed from the access opening. Walking surfaces and low clearance limited access.</p>', "limit"),
    ("Attic & insulation", "Insulation", "Insulation coverage", '<p>Visible insulation coverage is uneven at the noted area. Consult a qualified contractor about improving coverage.</p>', "defect"),
    ("Attic & insulation", "Ventilation", "Ventilation reference", '<p>See <a href="https://www.energy.gov/energysaver/ventilation">ventilation guidance</a> for general background. This link is retained as part of the comment.</p>', "info"),
    ("Attic & insulation", "Ventilation", "Rich content preservation sample", '<p style="color: #4b613d; font-weight: bold">Sample: “Exact wording” &amp; punctuation.</p><p>Line one.<br>Line two.</p>', "info"),
]


def main():
    target = Path(__file__).resolve().parents[1] / "examples" / "residential-demo.html-text.csv"
    target.parent.mkdir(exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Section Name", "Item Name", "Comment Name", "Comment Text", "Comment Type (info, limit, defect)", "Category (-1: Low, 0: Med, 1: High)", "Order (w/i item)"])
        previous = None
        order = 0
        for section, item, name, html, kind in ROWS:
            key = section, item
            order = order + 1 if key == previous else 1
            previous = key
            writer.writerow([section, item, name, html, kind, "0" if kind == "defect" else "", order])
    print(f"Created synthetic fixture: {target.name} ({len(ROWS)} comments)")


if __name__ == "__main__":
    main()
