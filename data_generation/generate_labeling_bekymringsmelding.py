import os
import re
import time
import json
import random
import signal
import sys
import threading
from datetime import datetime, timedelta

from dotenv import load_dotenv
import google.generativeai as genai

"""
Combined script for generating and labeling Norwegian 'bekymringsmeldinger' (concern reports).
This script handles both generation of reports and their subsequent labeling with sensitive data extraction.
"""

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', '.env'))

# Configuration
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# Define data folders
MAIN_FOLDER = os.path.join(os.path.dirname(__file__), 'bekymringsmelding')
DATA_FOLDER = os.path.join(MAIN_FOLDER, 'bekymringsmelding_text')
TRAINING_FOLDER = os.path.join(MAIN_FOLDER, 'labeling_bekymringsmelding')
PROCESSED_FOLDER = os.path.join(DATA_FOLDER, 'processed')

# Create necessary directories
for folder in [MAIN_FOLDER, DATA_FOLDER, TRAINING_FOLDER, PROCESSED_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"Created directory: {folder}")

# Flag to control threads
running = True

# Define scenarios for concern reports
concern_scenarios = [
    # Animal welfare concerns
    "A small dog that barks constantly for several hours each day, living in an apartment. Neighbor suspects neglect and possible drug use by the owner.",
    "A horse that appears severely underweight and is kept in a too-small enclosure without proper shelter or water.",
    "Multiple cats living in a cluttered home with strong smell of urine and feces. The owner seems to be a hoarder.",
    "Chickens kept in small, dirty cages in a residential backyard without proper food or water.",
    "A dog left outside on a balcony regardless of weather conditions, often heard whimpering.",
    "Several rabbits kept in tiny cages in a garage, appearing malnourished.",
    "A parrot that seems distressed, constantly plucking its feathers, kept in a small cage in a noisy environment.",
    "Farm animals (sheep) appearing neglected, with no access to food and water during winter.",
    "Puppies being sold from a car trunk at a parking lot, appearing sick and lethargic.",
    "A chained dog without shelter in a rural property, visible ribs and matted fur.",

    # Food safety concerns
    "A restaurant employee reports unsafe food handling practices and rat infestation in the kitchen.",
    "A consumer found foreign objects in packaged meat bought from a local supermarket.",
    "A bakery that operates without proper hygiene measures, with staff not using gloves or hairnets.",
    "A food truck that doesn't have refrigeration for dairy and meat products.",
    "A catering business operating from a private home without proper food safety certifications.",
    "A grocery store selling expired dairy products with altered date labels.",
    "A slaughterhouse employee reports animals being processed without proper inspection.",
    "A fishmonger selling fish that smells strongly of ammonia and appears discolored.",
    "A food processing facility with evidence of pest infestation and poor cleaning routines.",
    "A farmer's market vendor selling unpasteurized dairy products without proper labeling or warnings.",

    # Plant health concerns
    "A plant nursery suspected of importing exotic plants without quarantine measures.",
    "An outbreak of a plant disease in a neighborhood traced to a local garden center.",
    "A farmer using banned pesticides on vegetable crops meant for market.",
    "Trees showing signs of ash dieback disease in a municipal park.",
    "A suspected case of potato wart disease in a commercial farming operation.",

    # Mixed concerns
    "A petting zoo with visibly sick animals and poor sanitation near food service areas.",
    "A farm with evidence of both animal neglect and improper use of agricultural chemicals.",
    "A household with children where dangerous dogs are kept without proper restraint or training.",
    "A rural property where exotic animals are being bred without proper permits or care.",
    "A supermarket with persistent food safety violations and employee reports of management intimidation."

    # Additional scenarios 
    "Neighbor's dog barking constantly for many hours each day, owners rarely home",
    "Multiple cats living in a small apartment with visible signs of neglect and poor hygiene",
    "Horse appears severely underweight with no access to adequate shelter",
    "Pet rabbits kept in tiny cages outside during winter with no protection from elements",
    "Dog left alone on balcony in all weather conditions, visibly distressed",
    "Exotic birds kept in cramped cages, showing signs of stress and feather plucking",
    "Farm animals without access to clean water or sufficient food",
    "Dog being trained with harsh punishment methods and physical abuse",
    "Pet shop selling visibly sick animals and keeping them in poor conditions",
    "Elderly person with too many animals they cannot properly care for",
    "Animals kept in basement with no natural light or adequate ventilation",
    "Dog always chained outside with minimal shelter regardless of weather",
    "Puppies being bred in unhygienic conditions with signs of illness",
    "Neighbor intoxicated while caring for animals, neglecting basic needs",
    "Farm with dead animals visible and others appearing severely neglected",
    "Animals abandoned in apartment after owner moved out",
    "Dog showing signs of physical abuse, owner aggressive when confronted",
    "Reptiles kept without proper heating or appropriate enclosures",
    "Circus animals showing signs of stress and confined to small cages",
    "Animals kept in vehicle for extended periods during hot/cold weather",
    "Livestock transported in overcrowded conditions without water",
    "Wildlife illegally kept as pets in unsuitable environments",
    "Chickens kept in overcrowded coops with no access to outdoor space",
    "Dog always muzzled even when eating or drinking",
    "Animals in rural property with no shelter during harsh winter conditions",
    "Neighbor hoarding multiple dogs in small apartment with strong odor",
    "Dog constantly left alone in car regardless of temperature",
    "Sheep visibly ill with no veterinary care provided",
    "Pet birds kept in tiny cages unable to spread wings",
    "Animals used in illegal fighting activities showing injuries",
    "Dog always appears underfed with ribs clearly visible",
    "Livestock with untreated injuries or visible health problems",
    "Animals in traveling petting zoo showing signs of stress and poor health",
    "Rodents kept in overcrowded containers at pet store",
    "Horses in paddock with dangerous objects and inadequate fencing",
    "Animals showing signs of severe dental problems without treatment",
    "Dog with chronic skin condition left untreated",
    "Neighbor witnessed hitting or kicking animals repeatedly",
    "Cats kept exclusively indoors in unhygienic conditions",
    "Dairy cows with untreated mastitis or lameness issues",
    "Aquarium fish kept in dirty, overcrowded tanks",
    "Pregnant or nursing animals without appropriate care",
    "Animals showing signs of poisoning or toxic exposure",
    "Working dogs kept in inappropriately small kennels",
    "Goats with overgrown hooves causing mobility issues",
    "Pet monkeys or other primates kept in household environments",
    "Hunting dogs kept in poor conditions between hunting seasons",
    "Dog showing signs of illegal ear cropping or tail docking",
    "Animals at small zoo facility with inadequate enclosures",
    "Neighbor's animals with chronic untreated medical conditions",
    "Pigs kept in muddy conditions without dry resting areas",
    "Pet store selling underage puppies or kittens",
    "Working horses showing signs of overexertion and exhaustion",
    "Animals at boarding facility left unattended for extended periods",
    "Dog constantly wearing shock collar with visible neck irritation",
    "Injured wildlife kept rather than taken to rehabilitation center",
    "Sheepdogs living permanently with flock without adequate care",
    "Animals at small farm deprived of social contact with own species",
    "Dog left outside during extreme temperatures without shelter",
    "Animals in research facility with conditions violating regulations",
    "Pet owner exhibiting signs of mental illness affecting animal care",
    "Animals being fed inappropriate or insufficient diet",
    "Livestock without access to shelter during extreme weather",
    "Horse with signs of overwork and inappropriate equipment use",
    "Hunting dogs trained using cruel or abusive methods",
    "Pets belonging to drug users showing signs of neglect",
    "Animals at educational facility kept in inadequate conditions",
    "Livestock with severe parasite infestations left untreated",
    "Dog consistently tied up in yard in its own waste",
    "Birds in aviary with broken wings or other untreated injuries",
    "Cattle with untreated eye infections or other visible health issues",
    "Animals belonging to elderly owner who cannot provide proper care",
    "Dog aggressive due to inappropriate training or mistreatment",
    "Exotic reptiles kept without necessary heat sources",
    "Severely matted animals causing skin issues and discomfort",
    "Animals in therapeutic program showing signs of stress or overwork",
    "Neighbor threatening to harm animals during disputes",
    "Pets left alone during owner's extended hospital stay",
    "Animals showing signs of starvation or severe dehydration",
    "Multiple dogs kept in garage or shed without proper ventilation",
    "Horses with untreated lameness issues still being ridden",
    "Organized animal fighting ring with injured animals",
    "Dog kept in crate most of the day, every day",
    "Goats with no access to climbing structures or enrichment",
    "Puppies sold online from breeder with poor conditions",
    "Animals used for street performances showing signs of stress",
    "Neighbor witnessed throwing objects at animals",
    "Dog always wearing prong collar causing visible discomfort",
    "Animals at small dairy farm in unhygienic milking conditions",
    "Dog with severe anxiety left alone for extended periods daily",
    "Sheep with heavy wool coats during summer months",
    "Animals repeatedly escaping due to inadequate containment",
    "Dog living in car with owner who appears homeless",
    "Animals with open wounds or injuries left untreated",
    "Ponies used for children's rides showing signs of exhaustion",
    "Animals kept in construction site without proper shelter",
    "Multiple animals in household affected by untreated parasites"
]

names = [
    "Anders Johansen", "Ingrid Berg", "Morten Olsen", "Silje Pedersen", "Henrik Nilsen",
    "Astrid Hansen", "Petter Kristiansen", "Tone Larsen", "Lars Andersen", "Kari Svendsen",
    "Geir Eriksen", "Mette Jensen", "Thomas Dahl", "Hanne Bakken", "Bjørn Haugen",
    "Marianne Hagen", "Knut Iversen", "Ida Jørgensen", "Fredrik Moen", "Camilla Nygård",
    "Jørgen Solberg", "Lene Sørensen", "Svein Lund", "Bente Karlsen", "Kjell Berntsen",
    "Elin Halvorsen", "Magnus Arnesen", "Hilde Jacobsen", "Håkon Rasmussen", "Liv Gundersen",
    "Trond Pettersen", "Anette Strand", "Rune Myhre", "Ellen Tangen", "Ole Johnsen",
    "Kristin Sandberg", "Arne Ødegård", "Marit Lie", "Jon Thomassen", "Ingvild Hoff",
    "Terje Aasen", "Lise Gulbrandsen", "Per Amundsen", "Heidi Evensen", "Ove Brekke",
    "Linda Davidsen", "Øyvind Fredriksen", "Anita Holm", "Stig Isaksen", "Tove Fossum",
    "Steinar Mikkelsen", "Eva Næss", "Frode Ellingsen", "Gro Andresen", "Ivar Antonsen",
    "Berit Paulsen", "Arild Berger", "Inger Hauge", "Espen Aas", "Wenche Martinsen",
    "Leif Wang", "Ann Christensen", "Tor Knudsen", "Ragnhild Bøe", "Roar Wold",
    "Nina Danielsen", "Johan Helland", "Randi Borge", "Nils Viken", "Anne Bjørndal",
    "Sverre Holmen", "Gunn Eide", "Vidar Ruud", "Karin Hovland", "Odd Jenssen",
    "Maria Sæther", "Roger Løkken", "Solveig Stene", "Hans Blix", "Monica Kolstad",
    "Åge Vik", "Elisabeth Aamodt", "Jan Myreng", "Tonje Fjeld", "Erling Bakke",
    "Kristine Skar", "Karl Vang", "Grethe Solheim", "Jostein Rønning", "Torhild Haugland",
    "Einar Nordby", "Sigrid Dahlen", "Øystein Aune", "Laila Fosse", "Gunnar Brekken",
    "Trine Tveit", "Helge Mork", "Kirsti Ottesen", "Kåre Torp", "Synnøve Nyland",
    "Reidar Kvam", "Hege Bjerke", "Sigurd Sunde", "Mari Dybdahl", "Stein Sjøberg",
    "Turid Øien", "Ola Foss", "Vigdis Hagen", "Torgrim Molvik", "Olaug Hegge",
    "Gunnar Østby", "Grete Norheim", "Asbjørn Knutsen", "Siri Teigen", "Thorbjørn Enger",
    "Emma Sætre", "Birger Sande", "Aud Holter", "Dagfinn Haaland", "Birgitte Rød",
    "Finn Graff", "Maiken Solås", "Halvard Thue", "Louise Åsheim", "Sigbjørn Næss",
    "Tove Fjellheim", "Egil Brattbakk", "Mona Haug", "Yngve Hovde", "Elsa Langeland",
    "Jakob Løvstad", "Irene Brekka", "Oddvar Røed", "Ingebjørg Stokke", "Christian Hodne",
    "Unni Reiersen", "Arne Øvergård", "Jorunn Våge", "Tormod Nes", "Rigmor Krogh",
    "Eivind Morken", "Rita Kvamme", "Olav Dalland", "Else Selnes", "Ragnar Ødegaard",
    "Hannah Wilhelmsen", "Eirik Thorsen", "Gerd Sundby", "Bård Enger", "Lisbeth Fjell",
    "Vegard Ludvigsen", "Kjersti Skorpen", "Einar Kvalheim", "Sara Vestby", "Leif Stensrud",
    "Astri Krogstad", "Bent Aasen", "Ingeborg Hasund", "Arnfinn Holstad", "Vibeke Moen",
    "Sondre Lundekvam", "Ragnhild Nesdal", "Karsten Engh", "Elin Wangen", "Torstein Kleiven",
    "Lene Nordhaug", "Magne Erdal", "Åshild Bøhn", "Rolf Walle", "Sissel Røsvik",
    "Inge Nordvik", "Aina Haakestad", "Atle Marøy", "Brit Forsberg", "Gunnar Kleven",
    "Vilde Gustavsen", "Ottar Langås", "Eli Skogstad", "Aksel Smestad", "Eldbjørg Samuelsen",
    "Mads Vangen", "Toril Hole", "Jonas Nordstrand", "Anniken Bratsberg", "Geir Einvik",
    "Merethe Dahlberg", "Øivind Brandtzæg", "Janne Lilleby", "Harald Vesterheim", "Agnes Mølster",
    "Sturla Storli", "Cecilie Skogen", "Ingvar Waaler", "Ruth Nordrum", "Stian Tobiassen",
    "Astrid Langseth", "Erlend Hvattum", "Gina Finstad", "Halvor Wangensteen", "Beate Nygård",
    "Emil Skoglund", "Marte Tangen", "Bjarne Lysø", "Ingrid Hammer", "Roy Bekkelund",
    "Synne Kristoffersen", "Frode Vangen", "Sigrid Haavik", "Pål Kvalsvik", "Mia Bryhn",
    "Trygve Hermansen", "Tone Stensvold", "Simen Tjelta", "Ingunn Fjærestad", "Oddbjørn Haakonsen",
    "Live Westlie", "Erling Stavnes", "Heidi Bratli", "Torbjørn Kvale", "Veronica Kvaale",
    "Kjetil Haraldsen", "Stine Aakvik", "Odd-Arne Jacobsen", "Julie Strandheim", "Knut-Erik Solheim",
    "Mariann Tønsberg", "Gaute Grønbeck", "Aina Folkestad", "Steffen Leknes", "Elise Kverneland",
    "Sigve Tjørhom", "Kathrine Bergsland", "Kolbjørn Nordlien", "Tanja Huse", "Olaf Bergum",
    "Martine Hegland", "Peder Røssland", "Marita Holstad", "Kjartan Bjørge", "Anette Ringdal",
    "Runar Helgheim", "Tina Børresen", "Brage Ødegården", "Mona Hjelm", "Oddvin Breivik",
    "Sissel Nygårdsvold", "Ståle Mæhle", "Janne Bjelland", "Jens-Petter Stokkeland", "Marthe Strøm",
    "Kenneth Dalseth", "Frida Wallin", "Audun Hvidsten", "Grethe Rosseland", "Carl-Fredrik Wisløff",
    "Siw Holmsen", "Christopher Kildal", "Jorun Vestly", "Håvard Stangeland", "Linn Strømme",
    "Øystein Tvedten", "Oda Røen", "Morten Seljeflot", "Vera Solbakken", "Fridtjof Møller",
    "Cathrine Lunde", "Aslak Bjørnstad", "Sofia Engelsen", "Torgeir Skaug", "Åse Haagensen",
    "Filip Skogland", "June Valheim", "Eirik Steinsland", "Rebecca Skrede", "Ole-Martin Ekeberg",
    "Charlotte Skjønberg", "Sindre Finnerud", "Veronika Kvalnes", "Adrian Selmer", "Jenny Tvete",
    "Henrik Bøe", "Maren Bjerke", "Isak Lillevik", "Emilie Thorvaldsen", "Nicolai Olaussen",
    "Sunniva Krogsæter", "Torbjørn Midtbø", "Natalie Berge", "August Rønningen", "Caroline Nesse",
    "Jo Gimse", "Karoline Tvedt", "Eskil Nordgård", "Victoria Solvang", "Edvard Guddal",
    "Thea Leithe", "Robin Sandvik", "Helene Gjerstad", "Sander Lier", "Guro Høyland",
    "Kristoffer Aune", "Silje Bredesen", "Daniel Hjortland", "Elise Sønstebø", "Markus Slettebø",
    "Nora Gravdal", "Julian Horne", "Ida Mathisen", "Vebjørn Stokstad", "Amanda Hegna",
    "Preben Rossland", "Linn Kittilsen", "Vetle Gjertsen", "Sofie Bergseth", "Herman Brekken",
    "Malin Nysæter", "Mathias Lindgren", "Andrea Uthaug", "Kevin Bergstrøm", "Pernille Kaspersen",
    "William Nordgaard", "Marie Heggestad", "Simon Teigland", "Maja Guldberg", "Jørgen Furuhaug",
    "Thea Hasselberg", "Tobias Skogly", "Oda Borchgrevink", "Marcus Vetrhus", "Martine Eidem",
    "Dennis Flatland", "Sara Moseng", "Oliver Haugland", "Amalie Røise", "Sebastian Aakre",
    "Tuva Nicolaisen", "Eirik Svarstad", "Ingeborg Melhuus", "Sondre Trydal", "Helene Skarre",
    "Elias Vetrhus", "Maria Bjørnstad", "Kasper Ringheim", "Julie Grønvold", "Jonas Frøystad",
    "Hannah Hesjedal", "Emil Tjøstheim", "Mathilde Ramberg", "Sander Tønnesen", "Nora Hildre",
    "Kristian Moltu", "Mina Kavli", "Andreas Haukaas", "Vilde Mikkelsen", "Håkon Høiseth",
    "Selma Ulstein", "Aleksander Skartveit", "Ingrid Skogvang", "Noah Brandal", "Amalie Holme",
    "Magnus Tønsberg", "Tiril Rundhaug", "Jonas Olaisen", "Frida Bakkelund", "Henrik Voldsund",
    "Hedda Bakkehaug", "Fredrik Midtbø", "Mia Erlandsen", "Marius Svarverud", "Emma Bergesen",
    "Mathias Wahlstrøm", "Lea Bruland", "Vebjørn Erlandsen", "Linnea Lindås", "Noah Nordhaug",
    "Sophie Waage", "Markus Skjerve", "Ingvild Rognes", "Elias Liabø", "Aurora Nordengen",
    "Lukas Vetleseter", "Andrea Dalland", "Felix Korsvik", "Malin Skretteberg", "Jonathan Kittilsen",
    "Nathalie Bakketun", "Tobias Bergum", "Hedvig Rosseland", "Philip Indrekvam", "Emilie Nøttveit",
    "Mads Engelsen", "Thale Fredheim", "Herman Brunborg", "Sofie Holsether", "Joakim Flaaten",
    "Lykke Halvorsen", "Ulrik Rosenvinge", "Madeleine Løvås", "Johannes Solstad", "Maja Vangen",
    "Marius Skatteboe", "Frøya Sævareid", "Theo Kvernevik", "Oline Endresen", "Didrik Ellingsen",
    "Martine Kvamsdal", "Storm Husabø", "Ella Skarsgard", "Erik Mathiassen", "Ada Nordheim",
    "Felix Kleppestø", "Linnea Rustad", "Leonard Fiskerstrand", "Hermine Aamodt", "Benjamin Øverli",
    "Tuva Martinussen", "Leon Kirkebø", "Mina Lilleheier", "Victor Svartdal", "Synne Reiersen",
    "Gustav Helleland", "Mathea Løvlien", "Aksel Bjerkan", "Fride Tandberg", "Theodor Ulvestad",
    "Johanne Midttun", "Samuel Woldseth", "Alma Brandtzæg", "Oscar Klokkerhaug", "Tiril Løtveit",
    "Ferdinand Støylen", "Selma Leikvoll", "Emil Stavenes", "Dorthea Hopsdal", "Vincent Haakonsen",
    "Nathalie Sørheim", "Trym Vangsnes", "Amelia Ringseth", "Isak Løvlid", "Hedda Wilhelmsen",
    "Magnus Eidsheim", "Ylva Oterhals", "Kasper Langeland", "Saga Blindheim", "Lucas Valkner",
    "Ellen Grindheim", "Adrian Thingnes", "Erle Skjerven", "Henrik Nyland", "Vår Moldestad",
    "Johan Steinnes", "Thea Sandanger", "Even Bakkehaug", "Iben Gudmestad", "Kristoffer Nyhus",
    "Amanda Brekkhus", "Brage Vestbø", "Aurora Sørby", "William Sæthre", "Nora Skoglund",
    "Matheo Korneliussen", "Leah Eikemo", "Axel Bjelland", "Mia Helgeland", "Simen Sundal",
    "Tuva Gravdal", "Niklas Fauske", "Maja Halvorsen", "Jakob Gangstø", "Ingrid Håkonsen",
    "Sigurd Aase", "Vilde Solsvik", "Jesper Sandbakken", "Emma Viste", "Magnus Kjellevold",
    "Andrea Kvalheim", "Håkon Kolderup", "Malin Hageberg", "Oliver Nymo", "Linnea Stokken",
    "Filip Kirkevold", "Sofie Langaas", "Jonathan Hetland", "Oda Steinsvik", "Nicholas Kvalsund",
    "Hermine Bergseth", "Simon Strømmen", "Tuva Haavik", "Sebastian Solum", "Ida Rønnestad",
    "Marius Engebretsen", "Sara Sellevold", "Eskil Skjæveland", "Malin Nordgård", "Peder Sørensen",
    "Elise Hovland", "Gabriel Lilleaas", "Amanda Fuglerud", "Benjamin Hegland", "Helene Midtun",
    "Vetle Frøseth", "Marie Wangberg", "Kristoffer Brekkhus", "Sophie Skjæret", "Henrik Folkestad",
    "Ingeborg Vikanes", "Jonas Lilleeng", "Victoria Selvik", "Elias Thoresen", "Guro Eidsvoll",
    "Matheo Lieng", "Amalie Sletten", "Marcus Helliesen", "Frida Lorentzen", "Tobias Engdal",
    "Mina Gudmundsen", "Kasper Fagerheim", "Julie Hjelmeland", "Emil Hatlestad", "Nora Dalsbø",
    "Sander Monsen", "Thea Hovden", "Håkon Korsnes", "Ella Svendsrud", "Vebjørn Austvik",
    "Sofie Vagle", "Henrik Ertsland", "Jenny Raastad", "Johannes Wangensteen", "Alma Gjelsvik",
    "Oskar Leiknes", "Eline Hagenes", "William Klemetsen", "Tuva Heimstad", "Ulrik Hovdal",
    "Lea Tønnessen", "Noah Huseby", "Amalie Sørlie", "Markus Bakkerud", "Selma Solbakk",
    "Theodor Ottesen", "Madeleine Holstad", "Viktor Nordtveit", "Mia Westgaard", "Edvard Hellerud",
    "Emma Sandtorv", "Mathias Skjold", "Aurora Mørkved", "Oliver Lysne", "Tilde Stenersen",
    "Jakob Hovland", "Martine Kaland", "Even Stokkebekk", "Hannah Midtdal", "Magnus Slåttelid",
    "Ingrid Syversen", "Lucas Otterlei", "Sophie Tveiten", "Johan Kleppestø", "Amanda Gjerdrum",
    "Simen Engeland", "Malin Tveit", "Herman Øverlier", "Andrea Skjønhaug", "Jonas Hatlen",
    "Emilie Drivenes", "Felix Bjørkum", "Thea Mæland", "Matheo Svenkerud", "Vilde Torgersen",
    "Trym Halstensen", "Nora Klemetsen", "Aksel Håheim", "Sofie Algrøy", "Isak Borgen",
    "Linnea Brekkaas", "Jonathan Einarsen", "Oline Opedal", "William Fauske", "Astrid Holmlund",
    "Victor Heimli", "Sara Flatøy", "Sebastian Hellevik", "Tuva Lundberg", "Kristoffer Støren",
    "Mathilde Nordmark", "Adrian Løvseth", "Thale Skogsberg", "Samuel Klingenberg", "Amalie Grimstad",
    "August Husøy", "Mia Gjertsen", "Elias Langnes", "Pernille Stensen", "Lukas Vestby",
    "Ingeborg Skjæveland", "Philip Føreland", "Frida Nordgård", "Sigurd Røiseland", "Maja Skjøtskift",
    "Mads Sørbø", "Lykke Nordengen", "Kasper Fagertun", "Hermine Rustand", "Sander Skogly",
    "Hedvig Eidsvåg", "Vetle Hallberg", "Synne Vangsnes", "Tobias Størseth", "Iben Tobiassen",
    "Marcus Nesheim", "Ella Rødland", "Erik Espeland", "Amanda Enstad", "Herman Bredesen",
    "Martine Vestøl", "Felix Thorshaug", "Hedda Rønnevik", "Johan Dalhus", "Frøya Skarstein",
    "Henrik Hjortdal", "Tuva Natland", "Sebastian Skogstad", "Selma Heggebø", "Emil Heldal",
    "Sophie Kvitnes", "Mathias Østby", "Nora Dalsbø", "Lucas Bjordal", "Ida Kvalsnes",
    "Adrian Duesund", "Mina Skogheim", "Oskar Engdal", "Vilde Revheim", "Noah Røsseland",
    "Emma Leikanger", "Jonas Holmefjord", "Maria Stokken", "William Heimdal", "Tiril Ohnstad",
    "Brage Langfeldt", "Lea Rønhovde", "Henrik Skrede", "Saga Kleppa", "Matheo Sønsteby",
    "Ingrid Mælen", "Jakob Skogvold", "Tuva Nordskag", "Niklas Hermansen", "Emilie Nysveen",
    "Simen Bjerkeli", "Aurora Haugom", "Oliver Brekkhus", "Victoria Bakkelund", "Eskil Eikås",
    "Jenny Kallevik", "Magnus Gjelsvik", "Mia Sandvær", "Alexander Hillestad", "Sophie Thorshaug",
    "Jonathan Ekroll", "Hermine Langaard", "Simon Håvarstein", "Oda Kvalsvik", "Kristoffer Hjelset",
    "Linnea Nyhagen", "Edvard Lervåg", "Thea Bjørkevoll", "Ferdinand Solvoll", "Amanda Kleveland",
    "Theodor Walseth", "Lykke Nordmark", "Viktor Tveito", "Malin Kvernevik", "Benjamin Klemetzen",
    "Julie Mæhlum", "Ulrik Hermstad", "Emma Stensland", "Vebjørn Rødland", "Thale Røyrvik",
    "Håkon Hovland", "Sofie Liabø", "Emanuel Bjørsvik", "Marta Hofseth", "Mads Grindheim",
    "Nora Fuglestad", "Elias Grøterud", "Andrea Bjørkås", "Marius Nordtveit", "Alma Skogbakken",
    "William Østrem", "Hedda Korsvik", "Johannes Refsnes", "Eline Grønås", "Alexander Skartun",
    "Leah Rønning", "Kasper Eidsheim", "Hermine Hageland", "Adrian Skauge", "Guro Refsland",
    "Markus Rødland", "Frida Hovland", "Jesper Heldal", "Mina Langeland", "Didrik Bjørnstad",
    "Tuva Tveitan", "Theo Lundekvam", "Aurora Hjelset", "Noah Eikeland", "Pernille Tveter",
    "Mathias Bjerknes", "Ingrid Stenseth", "Henrik Nygårdsvik", "Lea Selvik", "August Skålnes",
    "Hannah Vikanes", "Sebastian Rønnevik", "Vilde Leiknes", "Magnus Solheim", "Maja Sandøy",
    "Oscar Vangen", "Selma Lilleland", "Felix Kroknes", "Tuva Skjerdal", "Leon Hovland",
    "Ida Skogvang", "Jonas Bjørkhaug", "Marie Lillefosse", "Herman Skjæveland", "Emilie Vedvik",
    "Tobias Nesse", "Emma Skarstrand", "Nikolai Erikstad", "Julie Liland", "Matheo Hageberg",
    "Elise Ramstad", "Kasper Ødegård", "Oline Kallestad", "Oliver Skogstad", "Nora Nordstrand",
    "Trym Grindheim", "Amanda Reiersen", "Erik Opsahl", "Mina Torland", "Lucas Skogly",
    "Ingeborg Tvedt", "Sigurd Hammersland", "Sara Hovland", "Henrik Nøstdal", "Sofie Rødal",
    "Jacob Liland", "Tuva Holmedal", "Philip Fosseide", "Linnea Nygårdsvold", "Magnus Kleiven",
    "Ella Bjørndal", "Mathias Fossheim", "Vilde Blindheim", "William Svanevik", "Thea Hopland",
    "Elias Revheim", "Andrea Steinsvik", "Alexander Odden", "Madeleine Bakkerud", "Isak Hovstad",
    "Amalie Skogvang", "Jonas Skogheim", "Hermine Svensen", "Sander Tangen", "Emma Bruland",
    "Herman Svendsen", "Tuva Haugsvær", "Felix Brekkaas", "Mia Sjøvold", "Henrik Førland",
    "Ingrid Brækken", "Tobias Vangsnes", "Leah Heggestad", "Matheo Solberg", "Victoria Bjerkan",
    "Jakob Skogstad", "Sophie Skogmo", "Oskar Lindvik", "Mina Kalstad", "Ulrik Rognlien",
    "Nora Algrøy", "Emil Bredholt", "Martine Hatlen", "Johannes Hetland", "Ella Haaland",
    "Lucas Westrum", "Hermine Erlandsen", "Kristoffer Løkken", "Sara Vestbø", "Vetle Skogheim",
    "Thea Kaspersen", "William Ellingsen", "Oline Valheim", "Simen Stenvik", "Selma Aasland",
    "Sebastian Lervåg", "Vilde Røssland", "Jonas Egeland", "Mia Kaldestad", "August Skogvoll",
    "Emma Storevik", "Mathias Skogum", "Andrea Heide", "Alexander Breivik", "Frida Sørbøe",
    "Henrik Dalhaug", "Nora Skogstad", "Elias Skogdal", "Thale Kvernevik", "Magnus Nordmark",
    "Malin Egeland", "Sigurd Bergsland", "Hedda Halvorsen", "Johan Knarvik", "Tuva Olsvik",
    "Oliver Holstad", "Ingrid Skogland", "Tobias Soltveit", "Jenny Brekkenes", "Erik Nyhaven",
    "Lykke Langeland", "William Skogheim", "Maja Skognes", "Kasper Skogdal", "Iben Bjørnsen",
    "Matheo Halvorsen", "Sophia Lilleeng", "Jonas Vollen", "Amalie Breistein", "Edvard Hegna",
    "Frøya Skogsrud", "Herman Lindøe", "Marie Svensson", "Lukas Hovdal", "Astrid Heggland",
    "Felix Bergseng", "Ingeborg Brekkå", "Adrian Skogmo", "Tuva Lilleby", "Oskar Svendheim",
    "Madeleine Skoglund", "Henrik Bjørkli", "Linnea Fagerli"
]


# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    """Handle termination signals to shut down properly"""
    global running
    print("\nShutting down processes gracefully...")
    running = False

    # Give threads time to complete current operations
    time.sleep(2)
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# Generator functions
def generate_text(prompt, system_instruction):
    """Generate text using Gemini model with given prompt and system instruction"""
    model = genai.GenerativeModel("gemini-2.0-pro-exp-02-05", system_instruction=system_instruction)
    response = model.generate_content(prompt)
    return response.text


def save_to_txt(text, filename):
    """Save the generated text to a file after cleaning"""
    cleaned_text = clean_response(text)
    filepath = os.path.join(DATA_FOLDER, filename)
    with open(filepath, 'w', encoding='utf-8') as file:
        file.write(cleaned_text)
    return filepath


def clean_response(text):
    """Clean the response text from unwanted formatting"""
    # Remove [text] at the beginning and end
    text = re.sub(r'^\[\s*|\s*\]$', '', text.strip())
    # Remove all occurrences of '**'
    text = re.sub(r'\*\*', '', text)
    return text.strip()


def generate_date():
    """Generate a random date within the last 6 months"""
    today = datetime.now()
    days_ago = random.randint(1, 180)  # Within the last 6 months
    random_date = today - timedelta(days=days_ago)
    return random_date.strftime("%d.%m.%Y %H:%M")


# Labeling functions
def get_all_txt_files():
    """Retrieve all .txt files from DATA_FOLDER, sorted by creation time (oldest first)"""
    txt_files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.txt')]
    txt_files.sort(key=lambda f: os.path.getctime(os.path.join(DATA_FOLDER, f)))
    return txt_files


def clean_json_response(response_text):
    """Clean and parse the API response JSON"""
    cleaned_text = re.sub(r"```json\s*|\s*```", "", response_text).strip()

    try:
        data = json.loads(cleaned_text)
        if "text_input" in data and data["text_input"].endswith("["):
            data["text_input"] = data["text_input"].rstrip("[")
        return data
    except json.JSONDecodeError as e:
        print("JSON Decode Error:", e)
        print("Raw text that failed to parse:", cleaned_text[:200])  # Limited preview
        return {"error": "Invalid response from Gemini"}


def extract_sensitive_data(text):
    """Send text to Gemini API to extract and label sensitive data in structured format"""
    prompt = (
        "Analyze the following Norwegian 'bekymringsmelding' (concern report) and extract all sensitive entities according to the categories below. "
        "Ensure the output is a valid JSON format.\n\n"
        "**Sensitive Data Categories:**\n"
        "- **NO_PHONE_NUMBER** → Norwegian Phone Numbers\n"
        "- **PERSON** → Norwegian Names\n"
        "- **EMAIL_ADDRESS** → Email Addresses\n"
        "- **NO_ADDRESS** → Norwegian Home/Street Addresses\n"
        "- **DATE_TIME** → Dates and Timestamps\n"
        "- **GOV_ID** → Government-Issued Identifiers (any identification number)\n"
        "- **FINANCIAL_INFO** → Financial Data (contextually financial information, not just words about money)\n"
        "- **EMPLOYMENT_INFO** → Employment and Professional Details\n"
        "- **HEALTH_INFO** → Health-Related Information\n"
        "- **SEXUAL_ORIENTATION** → Sexual Relationships and Orientation\n"
        "- **CRIMINAL_RECORD** → Crime-Related Information\n"
        "- **CONTEXT_SENSITIVE** → Context-Sensitive Information\n"
        "- **IDENTIFIABLE_IMAGE** → Any Identifiable Image Reference\n"
        "- **FAMILY_RELATION** → Family and Relationship Data\n"
        "- **BEHAVIORAL_PATTERN** → Behavioral Pattern Data\n"
        "- **POLITICAL_CASE** → Political-Related Cases\n"
        "- **ECONOMIC_STATUS** → Economic Information\n"
        "- **POSTAL_CODE** → Norwegian Postal Codes\n\n"
        "### **Expected JSON Output Format:**\n"
        "{\n"
        '  "text_input": "Original text...",\n'
        '  "output": {\n'
        '    "PERSON": ["John Doe"],\n'
        '    "NO_ADDRESS": ["123 Main St"],\n'
        '    "POSTAL_CODE": ["12345"],\n'
        '    "NO_PHONE_NUMBER": ["123-456-7890"],\n'
        '    "EMAIL_ADDRESS": ["john.doe@email.com"],\n'
        '    "GOV_ID": ["12345678901"],\n'
        '    "EMPLOYMENT_INFO": ["Works as a teacher"]\n'
        "  }\n"
        "}\n"
        "**Ensure that the response is valid JSON without any Markdown syntax.**\n"
        f"Text: {text}"
    )

    model = genai.GenerativeModel("gemini-1.5-pro")
    response = model.generate_content(prompt)
    return response.text


# Main worker functions
def generator_worker():
    """Thread function to generate bekymringsmeldinger"""
    print("Starting generator worker...")
    while running:
        try:
            scenario = random.choice(concern_scenarios)

            name = random.choice(names)

            # Generate reference number
            reference = str(random.randint(100000, 999999))

            # Generate date
            report_date = generate_date()

            prompt = (
                f"Generate a Norwegian 'bekymringsmelding' (concern report) based on this scenario: {scenario}. "
                f"The report should start with bekymringsmelding mottatt av {names} without the : and it should mirror the structure and formatting typically used by Mattilsynet (Norwegian Food Safety Authority). "
                "Include realistic, detailed, but entirely fictional data including: "
                "Reporter's name, address, phone number, and email; "
                "Target of concern's information (if relevant); "
                "Details about the concern with specific observations; "
                "Format the report with these sections: "
                f"Subject: bekymringsmelding mottatt av {name}; It should be in teh first line for it's own!"
                "Mottatt (date and time); "
                "Type (concern type - e.g., Dyrevelferd, Mattrygghet, Plantehelse); "
                f"Referanse: {reference}; "
                "Navn på dyreeier eller virksomhet (target name if relevant); "
                "Adresse (complete Norwegian address); "
                "Fylke (county); "
                "Kommune (municipality); "
                "Poststed (postal code and city); "
                "Andre opplysninger (other information, can be any extra information that's need to be added for example 'the owner okonomi situation is not stable'. Note, this is just an example, and should be changed for everytime); "
                "Navn på varsler (reporter name); "
                "Telefon (reporter phone); "
                "E-post (reporter email); "
                "Anonym varsler (Nei or Ja); "
                "Sendt inn med vedlegg: should be changed for everytime for example 'Ja, bilder av dyrene'. Note, this is just an example, and should be changed for everytime); "
                "Then include these question-answer sections: "
                "-- Hvilket dyr er du bekymret for? Og hvor mange? -- (Which animal are you concerned about? And how many?); "
                "-- Hvordan ser dyrene ut? -- (How do the animals look?); "
                "-- Hvordan ser det ut der dyrene oppholder seg? -- (How does it look where the animals are kept?); "
                "-- Hvorfor mener du at dyrene ikke har det så bra? -- (Why do you think the animals are not doing well?); "
                "-- Hvordan kjenner du til dette? -- (How do you know about this?); "
                "-- Har du et yrke eller en spesiell rolle som Mattilsynet bør vite om? -- (Do you have a profession or special role that Mattilsynet should know about?). "
                "Important: Start and end your generated text with [ text ]. Every generation must be unique, realistic, and avoid common placeholder names like 'Ola Nordmann'."
            )

            system_instruction = (
                "You generate realistic Norwegian animal welfare concern reports (bekymringsmelding) following the precise MATS template. "
                "Always include rich, detailed personal information while maintaining the authentic structure and format of real Norwegian bekymringsmelding. "
                "Each report should describe a unique animal welfare concern situation with realistic details about both the animals and their conditions. "
                "Include specific details about the concerns such as neglect, poor living conditions, lack of food/water, excessive noise, signs of abuse, or other welfare issues. "
                "Create believable personal details for both the animal owner and the reporter, including realistic Norwegian names, addresses, contact information. "
                "Use proper Norwegian formatting for dates (DD.MM.YYYY), phone numbers, and addresses. "
                "Maintain a concerned but factual tone throughout the report, similar to how a real person would report an animal welfare concern."
            )

            generated_text = generate_text(prompt, system_instruction)

            timestamp = int(time.time())
            txt_filename = f"bekymringsmelding_{timestamp}.txt"
            filepath = save_to_txt(generated_text, txt_filename)

            print(f"Generated bekymringsmelding saved to {filepath}")

            # Wait to not overwhelm the API
            time.sleep(5)

        except Exception as e:
            print(f"Error in generator: {e}")
            time.sleep(5)


def labeler_worker():
    """Thread function to label bekymringsmeldinger"""
    print("Starting labeler worker...")

    # Give the generator a head start
    time.sleep(10)

    while running:
        try:
            txt_files = get_all_txt_files()

            if not txt_files:
                print("No files to process. Waiting...")
                time.sleep(10)
                continue

            # Process the oldest file
            txt_file = txt_files[0]
            file_path = os.path.join(DATA_FOLDER, txt_file)

            with open(file_path, 'r', encoding='utf-8') as file:
                report_text = file.read().strip()

            print(f"Labeling: {file_path}")
            raw_labeled_data = extract_sensitive_data(report_text)
            labeled_data = clean_json_response(raw_labeled_data)

            if "error" in labeled_data:
                print("Error in response:", labeled_data["error"])
                # Move to next file
                continue

            # Convert to JSONL format with proper Unicode encoding
            jsonl_entry = json.dumps({
                "text_input": labeled_data.get("text_input", "").encode("utf-8").decode("utf-8"),
                "output": labeled_data.get("output", {})
            }, ensure_ascii=False)  # Ensure readable characters (å, ø, æ, etc.)

            training_file = os.path.join(TRAINING_FOLDER, "bekymringsmelding.jsonl")

            # Append to training file
            with open(training_file, 'a', encoding='utf-8') as file:
                file.write(jsonl_entry + '\n')

            print(f"Labeled training data saved to {training_file}")

            # Move processed file to processed folder
            os.rename(file_path, os.path.join(PROCESSED_FOLDER, txt_file))
            print(f"Moved processed file to {PROCESSED_FOLDER}")

            # Wait between API calls to avoid rate limiting
            time.sleep(5)

        except Exception as e:
            print(f"Error in labeler: {e}")
            time.sleep(5)


if __name__ == "__main__":
    print("Starting bekymringsmelding generation and labeling system...")
    print(f"Data will be stored in: {DATA_FOLDER}")
    print(f"Labeled data will be stored in: {TRAINING_FOLDER}")

    # Start threads
    generator_thread = threading.Thread(target=generator_worker)
    labeler_thread = threading.Thread(target=labeler_worker)

    generator_thread.daemon = True
    labeler_thread.daemon = True

    generator_thread.start()
    labeler_thread.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)