from __future__ import annotations

import ast
import json
import math
import operator
import os
import random
import re
import time
from datetime import datetime, timedelta
from copy import deepcopy
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "group-travel-planner-dev-key")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyBrvfi0fVxXNCkKYyijPS7hL8tPTcuoEnI")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-18ce200274c94e5d8aeffcc337ad52d4").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
try:
    FAMOUS_SPOTS_CACHE_TTL_SEC = max(300, int(os.getenv("FAMOUS_SPOTS_CACHE_TTL_SEC", "21600")))
except ValueError:
    FAMOUS_SPOTS_CACHE_TTL_SEC = 21600
try:
    FAMOUS_SPOTS_RETRY_AFTER_SEC = max(60, int(os.getenv("FAMOUS_SPOTS_RETRY_AFTER_SEC", "300")))
except ValueError:
    FAMOUS_SPOTS_RETRY_AFTER_SEC = 300
FAMOUS_SPOTS_DISABLED_UNTIL = 0.0
FAMOUS_SPOTS_CACHE: dict[str, tuple[float, list[str]]] = {}
try:
    DISTANCE_CACHE_TTL_SEC = max(60, int(os.getenv("DISTANCE_CACHE_TTL_SEC", "900")))
except ValueError:
    DISTANCE_CACHE_TTL_SEC = 900
DISTANCE_RESULT_CACHE: dict[tuple[str, str, bool], tuple[float, dict[str, object]]] = {}

# In-memory user store for local demo login and password reset.
USER_STORE: dict[str, dict[str, str]] = {}
DEFAULT_QUICK_REPLIES = [
    "I visited this place, show nearby famous spots",
    "Visited place food recommendations",
    "Visited place activities with price",
    "Visited place nearby hotels with exact price",
    "Give advanced revisit plan for visited place",
    "Best month to revisit this place",
    "Best time to visit this destination",
    "Local transport options with fare",
    "Group safety checklist for this trip",
    "Packing essentials for this trip",
]

DESTINATION_PROFILES = {
    "goa": {
        "best_months": "October to March",
        "history_note": "Goa blends Portuguese colonial history with Konkan coastal culture.",
        "culture_note": "Music, seafood, beach festivals, and church heritage define local culture.",
        "attractions": [
            "Calangute and Baga beach belt",
            "Old Goa churches and heritage trail",
            "Fontainhas Latin quarter walk",
            "Dudhsagar day trip",
        ],
        "nearby_spots": [
            "Aguada Fort (18 km from Panaji)",
            "Chapora Fort (22 km from Panaji)",
            "Dona Paula viewpoint (7 km from Panaji)",
            "Colva Beach (34 km from Panaji)",
        ],
        "foods": [
            "Goan fish curry at Panaji local eateries",
            "Prawn balchao at beach shacks in Candolim",
            "Bebinca dessert at old bakery lanes in Panaji",
        ],
        "shopping": [
            "Azulejo tiles and handcrafted decor from Panaji boutiques",
            "Cashew and kokum products from local markets",
            "Beachwear and shell accessories from Anjuna flea market",
        ],
        "transport": [
            "Scooter rental: Rs 400-700/day",
            "Local cab: Rs 15-25 per km depending on zone",
            "Shared bus: Rs 30-80 per ride",
        ],
        "activities": [
            {"name": "Scuba diving - Grande Island", "price": 3500},
            {"name": "Parasailing - Calangute", "price": 1800},
            {"name": "Sunset cruise - Mandovi River", "price": 1200},
            {"name": "ATV ride - North Goa trails", "price": 1500},
        ],
        "hotels": [
            {"name": "Calangute Seabreeze Resort", "price": 4300, "rating": 4, "area": "Calangute"},
            {"name": "Panjim Riverside Hotel", "price": 3900, "rating": 4, "area": "Panaji"},
            {"name": "Candolim Bay Retreat", "price": 5200, "rating": 5, "area": "Candolim"},
            {"name": "Anjuna Palm Residency", "price": 3600, "rating": 4, "area": "Anjuna"},
            {"name": "Benaulim Dunes Stay", "price": 3400, "rating": 4, "area": "Benaulim"},
        ],
    },
    "manali": {
        "best_months": "March to June and September to November",
        "history_note": "Manali evolved from a Himalayan trade stop into a major adventure destination.",
        "culture_note": "The region carries Himachali traditions, wooden temples, and mountain village life.",
        "attractions": [
            "Solang Valley activities",
            "Old Manali cafe lane",
            "Naggar Castle viewpoint",
            "Atal Tunnel day drive",
        ],
        "nearby_spots": [
            "Hadimba Temple (2 km from Mall Road)",
            "Vashisht hot springs (4 km from Mall Road)",
            "Jogini Falls trail (5 km from Vashisht)",
            "Sissu valley viewpoint (42 km via Atal Tunnel)",
        ],
        "foods": [
            "Siddu at old town cafes",
            "River trout meals near Vashisht",
            "Himachali dham at local family restaurants",
        ],
        "shopping": [
            "Woolen shawls and Kullu caps near Mall Road",
            "Handmade soaps and local oils in Old Manali",
            "Dry fruits and mountain honey from Himachali stores",
        ],
        "transport": [
            "Local cab half-day: Rs 1800-2500",
            "Bike rental: Rs 1200-1800/day",
            "Shared local bus: Rs 20-70 per ride",
        ],
        "activities": [
            {"name": "Paragliding - Solang", "price": 3200},
            {"name": "River rafting - Beas", "price": 1500},
            {"name": "Snow scooter ride - Solang", "price": 1800},
            {"name": "Zipline - adventure park", "price": 1200},
        ],
        "hotels": [
            {"name": "Snowline View Resort", "price": 4100, "rating": 4, "area": "Near Mall Road"},
            {"name": "Beas River Retreat", "price": 4600, "rating": 4, "area": "Vashisht Road"},
            {"name": "Pine Crest Manali", "price": 5200, "rating": 5, "area": "Old Manali"},
            {"name": "Solang Meadow Stay", "price": 3800, "rating": 4, "area": "Solang Route"},
            {"name": "Himalayan Nest Hotel", "price": 3400, "rating": 4, "area": "Prini"},
        ],
    },
    "jaipur": {
        "best_months": "October to February",
        "history_note": "Jaipur is the planned Pink City of Rajasthan, shaped by Rajput royal heritage.",
        "culture_note": "Forts, crafts, folk performances, and royal cuisine define city identity.",
        "attractions": [
            "Amer Fort",
            "City Palace and Hawa Mahal",
            "Nahargarh sunset viewpoint",
            "Local bazaar shopping trail",
        ],
        "nearby_spots": [
            "Jal Mahal (6 km from City Palace)",
            "Albert Hall Museum (2 km from Hawa Mahal)",
            "Jaigarh Fort (15 km from old city)",
            "Patrika Gate (11 km from City Palace)",
        ],
        "foods": [
            "Dal bati churma in old city thali houses",
            "Laal maas in heritage restaurants",
            "Ghewar from traditional sweet shops",
        ],
        "shopping": [
            "Blue pottery and block-print textiles in Bapu Bazaar",
            "Lac bangles and handcrafted jewelry in Johari Bazaar",
            "Mojari footwear and miniature art in old city lanes",
        ],
        "transport": [
            "E-rickshaw old city loop: Rs 250-500",
            "Cab city day package: Rs 2000-2800",
            "Metro + auto combo for short hops: Rs 20-200",
        ],
        "activities": [
            {"name": "Amer Fort light-and-sound show", "price": 600},
            {"name": "City e-rickshaw heritage circuit", "price": 900},
            {"name": "Rajasthani folk evening", "price": 1500},
            {"name": "Hot air balloon view ride", "price": 12000},
        ],
        "hotels": [
            {"name": "Pink City Palace View", "price": 4400, "rating": 4, "area": "Bani Park"},
            {"name": "Amber Heritage Inn", "price": 3900, "rating": 4, "area": "Amer Road"},
            {"name": "Raj Mahal Courtyard", "price": 5600, "rating": 5, "area": "Civil Lines"},
            {"name": "Hawa Mahal Residency", "price": 3600, "rating": 4, "area": "MI Road"},
            {"name": "Nahargarh Heights Stay", "price": 3300, "rating": 4, "area": "Shastri Nagar"},
        ],
    },
    "mahabaleshwar": {
        "best_months": "October to June",
        "history_note": "Mahabaleshwar was developed as a hill station during the British era and is known for viewpoints and strawberry farms.",
        "culture_note": "The town blends Sahyadri hill culture, farm tourism, and traditional Maharashtrian food.",
        "attractions": [
            "Arthur's Seat Point",
            "Venna Lake",
            "Mapro Garden",
            "Wilson Point sunrise viewpoint",
        ],
        "nearby_spots": [
            "Pratapgad Fort (24 km from Mahabaleshwar)",
            "Lingmala Waterfall (6 km from market area)",
            "Panchgani Table Land (19 km)",
            "Kate's Point (7 km)",
        ],
        "foods": [
            "Strawberry with cream at Mapro Garden",
            "Corn pattice and fresh berry shakes at local stalls",
            "Maharashtrian thali in old market restaurants",
        ],
        "shopping": [
            "Strawberry crush, jams, and syrups from local farm stores",
            "Chikki and fudge from Mahabaleshwar market",
            "Handcrafted leather accessories and local honey",
        ],
        "transport": [
            "Local sightseeing cab (full day): Rs 2500-3500",
            "Shared jeep routes for Panchgani circuit: Rs 80-250",
            "Auto-rickshaw short rides near market: Rs 80-200",
        ],
        "activities": [
            {"name": "Venna Lake boating", "price": 450},
            {"name": "Horse riding at Table Land", "price": 700},
            {"name": "Sunrise trip to Wilson Point", "price": 500},
            {"name": "Pratapgad Fort guided visit", "price": 1200},
        ],
        "hotels": [
            {"name": "Valley Crown Mahabaleshwar", "price": 4200, "rating": 4, "area": "Main Market"},
            {"name": "Venna Lake Retreat", "price": 5100, "rating": 4, "area": "Near Venna Lake"},
            {"name": "Mapro Hills Stay", "price": 3600, "rating": 4, "area": "Panchgani Road"},
            {"name": "Pratap View Resort", "price": 5700, "rating": 5, "area": "Old Mahabaleshwar"},
            {"name": "Wilson Point Residency", "price": 3300, "rating": 4, "area": "Satara Road"},
        ],
    },
}


PLACE_KEY_ALIASES: dict[str, str] = {
    "alleppey": "alappuzha",
    "pondicherry": "puducherry",
    "new delhi": "delhi",
    "trivandrum": "thiruvananthapuram",
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "mysore": "mysuru",
    "banaras": "varanasi",
    "vizag": "visakhapatnam",
}

DESTINATION_SPOT_DATA: dict[str, str] = {
    "agra": "Taj Mahal|Agra Fort|Mehtab Bagh|Itmad-ud-Daulah Tomb",
    "ahmedabad": "Sabarmati Ashram|Adalaj Stepwell|Kankaria Lake|Sidi Saiyyed Mosque",
    "ajmer": "Ajmer Sharif Dargah|Ana Sagar Lake|Adhai Din Ka Jhonpra|Taragarh Fort",
    "alappuzha": "Alappuzha Beach|Vembanad Lake Backwaters|Alleppey Lighthouse|Pathiramanal Island",
    "alibaug": "Alibaug Beach|Kolaba Fort|Kashid Beach|Murud Janjira Fort",
    "alleppey": "Alappuzha Beach|Vembanad Lake Backwaters|Alleppey Lighthouse|Pathiramanal Island",
    "amritsar": "Golden Temple|Jallianwala Bagh|Wagah Border|Partition Museum",
    "auli": "Auli Ropeway|Gurso Bugyal|Chenab Lake Trek|Nanda Devi Viewpoint",
    "aurangabad": "Bibi Ka Maqbara|Ajanta Caves|Ellora Caves|Daulatabad Fort",
    "ayodhya": "Ram Janmabhoomi|Hanuman Garhi|Kanak Bhawan|Saryu Ghat",
    "badami": "Badami Cave Temples|Agastya Lake|Bhutanatha Temple|Pattadakal Group of Monuments",
    "bandhavgarh": "Bandhavgarh National Park Safari|Bandhavgarh Fort|Shesh Shaiya|Chakradhara Meadow",
    "bengaluru": "Lalbagh Botanical Garden|Bengaluru Palace|Cubbon Park|ISKCON Temple Bangalore",
    "bhopal": "Upper Lake|Van Vihar National Park|Bhimbetka Rock Shelters|Sanchi Stupa",
    "bhubaneswar": "Lingaraj Temple|Udayagiri and Khandagiri Caves|Nandankanan Zoological Park|Dhauli Shanti Stupa",
    "bikaner": "Junagarh Fort|Karni Mata Temple|Lalgarh Palace|National Research Centre on Camel",
    "chandigarh": "Rock Garden|Sukhna Lake|Rose Garden Chandigarh|Capitol Complex",
    "chennai": "Marina Beach|Kapaleeshwarar Temple|Fort St George|Government Museum Chennai",
    "cherrapunji": "Nohkalikai Falls|Seven Sisters Falls|Mawsmai Cave|Double Decker Living Root Bridge",
    "coimbatore": "Marudhamalai Temple|Adiyogi Shiva Statue|VOC Park and Zoo|Siruvani Waterfalls",
    "coorg": "Abbey Falls|Raja Seat|Dubare Elephant Camp|Namdroling Monastery",
    "dalhousie": "Khajjiar|Panchpula|Dainkund Peak|St John Church Dalhousie",
    "daman": "Devka Beach|Jampore Beach|Moti Daman Fort|Bom Jesus Church Daman",
    "darjeeling": "Tiger Hill Sunrise Point|Batasia Loop|Darjeeling Himalayan Railway|Padmaja Naidu Himalayan Zoological Park",
    "dehradun": "Robbers Cave|Sahastradhara|Forest Research Institute|Tapkeshwar Temple",
    "delhi": "Red Fort|India Gate|Qutub Minar|Humayun Tomb",
    "dharamshala": "Dalai Lama Temple|Bhagsu Waterfall|Triund Trek|St John in the Wilderness Church",
    "digha": "New Digha Beach|Marine Aquarium Digha|Udaipur Beach Digha|Amarabati Park",
    "diu": "Nagoa Beach|Diu Fort|Naida Caves|St Paul Church Diu",
    "dwarka": "Dwarkadhish Temple|Bet Dwarka|Rukmini Devi Temple|Dwarka Beach",
    "gangtok": "MG Marg|Rumtek Monastery|Tsomgo Lake|Nathula Pass",
    "goa": "Baga Beach|Basilica of Bom Jesus|Fort Aguada|Dudhsagar Falls",
    "gokarna": "Om Beach|Kudle Beach|Mahabaleshwar Temple Gokarna|Half Moon Beach",
    "gulmarg": "Gulmarg Gondola|Apharwat Peak|St Mary Church Gulmarg|Khilanmarg",
    "guwahati": "Kamakhya Temple|Umananda Island|Assam State Museum|Pobitora Wildlife Sanctuary",
    "gwalior": "Gwalior Fort|Jai Vilas Palace|Sas Bahu Temple|Teli Ka Mandir",
    "hampi": "Virupaksha Temple|Vittala Temple|Hampi Bazaar|Matanga Hill",
    "haridwar": "Har Ki Pauri|Mansa Devi Temple|Chandi Devi Temple|Bharat Mata Mandir Haridwar",
    "havelock island": "Radhanagar Beach|Elephant Beach|Kalapathar Beach|Neil Island Day Trip",
    "hyderabad": "Charminar|Golconda Fort|Ramoji Film City|Hussain Sagar Lake",
    "indore": "Rajwada Palace|Sarafa Bazaar|Lal Bagh Palace|Khajrana Ganesh Temple",
    "itanagar": "Ita Fort|Ganga Lake|Jawaharlal Nehru Museum Itanagar|Gompa Buddhist Temple",
    "jabalpur": "Bhedaghat Marble Rocks|Dhuandhar Falls|Chausath Yogini Temple|Madan Mahal Fort",
    "jaipur": "Amer Fort|City Palace Jaipur|Hawa Mahal|Jantar Mantar Jaipur",
    "jaisalmer": "Jaisalmer Fort|Sam Sand Dunes|Patwon Ki Haveli|Gadisar Lake",
    "jodhpur": "Mehrangarh Fort|Jaswant Thada|Umaid Bhawan Palace|Clock Tower Market Jodhpur",
    "kanchipuram": "Ekambareswarar Temple|Kailasanathar Temple|Kamakshi Amman Temple|Varadharaja Perumal Temple",
    "kanha": "Kanha National Park Safari|Bamni Dadar|Kanha Museum|Shravan Tal",
    "kannur": "St Angelo Fort|Muzhappilangad Drive-in Beach|Payyambalam Beach|Arakkal Museum",
    "kanpur": "JK Temple Kanpur|Allen Forest Zoo|Bithoor Ghat|Kanpur Memorial Church",
    "kanyakumari": "Vivekananda Rock Memorial|Thiruvalluvar Statue|Kanyakumari Beach|Sunset Point Kanyakumari",
    "kasol": "Parvati River Trail|Chalal Village Trek|Manikaran Sahib|Tosh Village",
    "katra": "Vaishno Devi Bhawan|Ardhkuwari Cave|Bhairavnath Temple|Jhajjar Kotli",
    "kaziranga": "Kaziranga National Park Safari|Kaziranga Orchid Park|Bagori Range|Kakochang Waterfall",
    "khajuraho": "Khajuraho Western Group Temples|Kandariya Mahadeva Temple|Raneh Falls|Panna National Park",
    "kochi": "Fort Kochi|Chinese Fishing Nets|Mattancherry Palace|Kerala Folklore Museum",
    "kodaikanal": "Coaker Walk|Kodaikanal Lake|Bryant Park|Pillar Rocks",
    "kohima": "Kohima War Cemetery|Kisama Heritage Village|Nagaland State Museum|Dzuku Valley Trek",
    "kolkata": "Victoria Memorial|Howrah Bridge|Dakshineswar Kali Temple|Indian Museum Kolkata",
    "kovalam": "Lighthouse Beach Kovalam|Hawa Beach|Samudra Beach|Vizhinjam Marine Aquarium",
    "kullu": "Raghunath Temple Kullu|Great Himalayan National Park|Bijli Mahadev Temple|Tirthan Valley",
    "kumarakom": "Kumarakom Bird Sanctuary|Vembanad Lake Cruise|Pathiramanal Island|Bay Island Driftwood Museum",
    "lakshadweep": "Agatti Island|Bangaram Island|Kavaratti Island|Kalpeni Island",
    "leh": "Shanti Stupa Leh|Leh Palace|Pangong Lake|Khardung La Pass",
    "lonavala": "Tiger Point Lonavala|Bhushi Dam|Karla Caves|Rajmachi Fort",
    "lucknow": "Bara Imambara|Rumi Darwaza|British Residency Lucknow|Ambedkar Memorial Park",
    "madurai": "Meenakshi Amman Temple|Thirumalai Nayakkar Palace|Gandhi Memorial Museum Madurai|Alagar Kovil",
    "mahabaleshwar": "Arthur Seat Point|Venna Lake|Mapro Garden|Wilson Point",
    "manali": "Hadimba Devi Temple|Solang Valley|Vashisht Hot Springs|Jogini Waterfall",
    "mangalore": "Panambur Beach|Kadri Manjunath Temple|St Aloysius Chapel|Sultan Battery",
    "mathura": "Shri Krishna Janmabhoomi|Dwarkadhish Temple Mathura|Vishram Ghat|Govardhan Hill",
    "mount abu": "Dilwara Temples|Nakki Lake|Guru Shikhar|Sunset Point Mount Abu",
    "mumbai": "Gateway of India|Marine Drive|Chhatrapati Shivaji Maharaj Terminus|Elephanta Caves",
    "munnar": "Tea Museum Munnar|Eravikulam National Park|Mattupetty Dam|Top Station",
    "mussoorie": "Kempty Falls|Gun Hill Point|Camel Back Road|Lal Tibba",
    "mysuru": "Mysore Palace|Chamundi Hills|Brindavan Gardens|St Philomena Church Mysuru",
    "nainital": "Naini Lake|Naina Devi Temple|Snow View Point|Tiffin Top",
    "nalanda": "Nalanda University Ruins|Hiuen Tsang Memorial Hall|Rajgir Hot Springs|Griddhakuta Hill",
    "nashik": "Trimbakeshwar Temple|Sula Vineyards|Panchavati|Saptashrungi Temple",
    "neemrana": "Neemrana Fort Palace|Baori Stepwell Neemrana|Zipline Neemrana|Sariska Day Excursion",
    "new delhi": "India Gate|Humayun Tomb|Lotus Temple|Rashtrapati Bhavan",
    "nubra valley": "Diskit Monastery|Hunder Sand Dunes|Panamik Hot Springs|Turtuk Village",
    "ooty": "Ooty Lake|Doddabetta Peak|Government Botanical Garden Ooty|Nilgiri Mountain Railway",
    "orchha": "Orchha Fort Complex|Chaturbhuj Temple|Ram Raja Temple Orchha|Betwa River Rafting",
    "patna": "Golghar|Takht Sri Patna Sahib|Bihar Museum|Buddha Smriti Park",
    "pelling": "Pemayangtse Monastery|Rabdentse Ruins|Sky Walk Pelling|Khecheopalri Lake",
    "pondicherry": "Promenade Beach Pondicherry|Auroville|Sri Aurobindo Ashram|Paradise Beach Pondicherry",
    "port blair": "Cellular Jail|Corbyn Cove Beach|Ross Island|North Bay Island",
    "puducherry": "Promenade Beach Pondicherry|Auroville|Paradise Beach Pondicherry|Manakula Vinayagar Temple",
    "pune": "Shaniwar Wada|Aga Khan Palace|Sinhagad Fort|Dagdusheth Halwai Ganpati Temple",
    "puri": "Jagannath Temple Puri|Golden Beach Puri|Konark Sun Temple|Chilika Lake",
    "pushkar": "Pushkar Lake|Brahma Temple Pushkar|Savitri Temple|Rangji Temple",
    "raipur": "Nandan Van Zoo|Mahant Ghasidas Memorial Museum|Purkhauti Muktangan|Ghatarani Waterfalls",
    "rameswaram": "Ramanathaswamy Temple|Dhanushkodi Beach|Pamban Bridge|APJ Abdul Kalam Memorial",
    "ranchi": "Dassam Falls|Hundru Falls|Rock Garden Ranchi|Jagannath Temple Ranchi",
    "ranikhet": "Jhula Devi Temple|Chaubatia Gardens|Bhalu Dam|Majhkhali Viewpoint",
    "ranthambore": "Ranthambore National Park Safari|Ranthambore Fort|Padam Talao|Surwal Lake",
    "rishikesh": "Laxman Jhula|Ram Jhula|Triveni Ghat Aarti|Neer Garh Waterfall",
    "saputara": "Saputara Lake|Sunset Point Saputara|Gira Waterfalls|Artist Village Saputara",
    "shillong": "Umiam Lake|Elephant Falls|Shillong Peak|Don Bosco Museum Shillong",
    "shimla": "The Ridge Shimla|Jakhu Temple|Mall Road Shimla|Kufri",
    "shirdi": "Sai Baba Samadhi Mandir|Dwarkamai|Chavadi|Shani Shingnapur",
    "somnath": "Somnath Temple|Triveni Sangam Somnath|Bhalka Tirth|Somnath Beach",
    "spiti": "Key Monastery|Chandratal Lake|Dhankar Monastery|Kibber Village",
    "srinagar": "Dal Lake|Mughal Gardens Srinagar|Shankaracharya Temple|Pari Mahal",
    "surat": "Dumas Beach|Sarthana Nature Park|Dutch Garden Surat|Science Centre Surat",
    "tawang": "Tawang Monastery|Sela Pass|Nuranang Falls|Madhuri Lake",
    "thanjavur": "Brihadeeswara Temple|Thanjavur Royal Palace|Saraswathi Mahal Library|Gangaikonda Cholapuram",
    "thekkady": "Periyar National Park|Periyar Lake Boating|Spice Plantation Thekkady|Kadathanadan Kalari Centre",
    "thiruvananthapuram": "Sree Padmanabhaswamy Temple|Kovalam Beach|Napier Museum|Poovar Island",
    "tirupati": "Tirumala Venkateswara Temple|Sri Kapileswara Swamy Temple|Talakona Waterfalls|Chandragiri Fort",
    "trivandrum": "Sree Padmanabhaswamy Temple|Kovalam Beach|Napier Museum|Shanghumugham Beach",
    "udaipur": "City Palace Udaipur|Lake Pichola|Sajjangarh Monsoon Palace|Jag Mandir",
    "ujjain": "Mahakaleshwar Jyotirlinga|Kal Bhairav Temple Ujjain|Ram Ghat Ujjain|Harsiddhi Temple",
    "vadodara": "Laxmi Vilas Palace|Sayaji Garden|EME Temple|Champaner-Pavagadh Archaeological Park",
    "varanasi": "Kashi Vishwanath Temple|Dashashwamedh Ghat|Sarnath|Assi Ghat",
    "varkala": "Varkala Cliff|Janardana Swami Temple|Papanasam Beach|Kappil Beach",
    "velankanni": "Basilica of Our Lady of Good Health|Velankanni Beach|Morning Star Church|Nagapattinam Lighthouse",
    "vijayawada": "Kanaka Durga Temple|Prakasam Barrage|Bhavani Island|Undavalli Caves",
    "visakhapatnam": "RK Beach|Kailasagiri|Yarada Beach|Submarine Museum Vizag",
    "vrindavan": "Prem Mandir|Banke Bihari Temple|ISKCON Vrindavan|Keshi Ghat",
    "wayanad": "Edakkal Caves|Soochipara Falls|Banasura Sagar Dam|Wayanad Wildlife Sanctuary",
    "yercaud": "Yercaud Lake|Pagoda Point|Killiyur Falls|Lady Seat",
    "ziro": "Ziro Valley|Talley Valley Wildlife Sanctuary|Kile Pakho|Meghna Cave Temple",
}

DESTINATION_SPOT_LIBRARY: dict[str, list[str]] = {
    key: [item.strip() for item in value.split("|") if item.strip()]
    for key, value in DESTINATION_SPOT_DATA.items()
}

ADDITIONAL_SPIRITUAL_SPOT_DATA: dict[str, str] = {
    "kedarnath": "Kedarnath Temple|Bhairavnath Temple Kedarnath|Adi Shankaracharya Samadhi|Vasuki Tal Trek",
    "badrinath": "Badrinath Temple|Tapt Kund|Mana Village|Charan Paduka",
    "gangotri": "Gangotri Temple|Bhagirathi Shila|Surya Kund Gangotri|Pandava Gufa",
    "yamunotri": "Yamunotri Temple|Surya Kund Yamunotri|Divya Shila|Janki Chatti",
    "amarnath": "Amarnath Cave Temple|Baltal Base Camp|Pahalgam Route|Sheshnag Lake",
    "vaishno devi": "Vaishno Devi Bhawan|Ardhkuwari Cave Temple|Bhairavnath Temple|Banganga Temple",
    "prayagraj": "Triveni Sangam|Hanuman Mandir Prayagraj|Alopi Devi Temple|Akshayavat Fort Campus",
    "bodh gaya": "Mahabodhi Temple|Bodhi Tree|Great Buddha Statue Bodh Gaya|Thai Monastery Bodh Gaya",
    "gaya": "Vishnupad Temple|Mangla Gauri Temple|Pretshila Hill|Brahmayoni Temple",
    "deoghar": "Baidyanath Jyotirlinga Temple|Naulakha Temple Deoghar|Tapovan Caves|Trikut Pahar",
    "srisailam": "Mallikarjuna Jyotirlinga Temple|Bhramaramba Temple|Srisailam Dam Viewpoint|Sakshi Ganapati Temple",
    "omkareshwar": "Omkareshwar Jyotirlinga|Mamleshwar Temple|Siddhanath Temple|Ahilya Ghat",
    "udupi": "Sri Krishna Matha Udupi|Anantheshwara Temple|Malpe Beach|St Mary Island",
    "guruvayur": "Guruvayur Sri Krishna Temple|Mammiyoor Temple|Punnathur Kotta Elephant Sanctuary|Parthasarathy Temple",
    "sabarimala": "Sabarimala Ayyappa Temple|Pamba Ganapathi Temple|Nilakkal Mahadeva Temple|Periyar Tiger Reserve Route",
    "palani": "Arulmigu Dhandayuthapani Swamy Temple|Palani Murugan Hill Temple|Idumban Temple|Thiru Avinankudi Temple",
    "thiruvannamalai": "Arunachaleswarar Temple|Girivalam Path|Virupaksha Cave|Skandashram",
    "chidambaram": "Nataraja Temple Chidambaram|Thillai Kali Temple|Pichavaram Mangroves|Annamalai University Zone",
    "kumbakonam": "Adi Kumbeswarar Temple|Sarangapani Temple|Airavatesvara Temple|Mahamaham Tank",
    "sringeri": "Sringeri Sharada Peetham|Vidyashankara Temple|Tunga River Ghat|Sri Malahanikareshwara Temple",
    "pandharpur": "Vithoba Rukmini Temple|Pundalik Temple|Chandrabhaga Ghat|Kaikadi Maharaj Math",
    "nanded": "Takht Hazur Sahib|Nanded Fort|Unkeshwar Hot Springs|Kandhar Fort",
    "anandpur sahib": "Takht Sri Keshgarh Sahib|Virasat-e-Khalsa|Anandgarh Fort|Charan Ganga",
    "hemkund sahib": "Hemkund Sahib Gurudwara|Lokpal Lakshman Temple|Ghangaria Base|Valley of Flowers Access",
    "bhimashankar": "Bhimashankar Jyotirlinga Temple|Hanuman Lake Bhimashankar|Gupt Bhimashankar|Bhimashankar Wildlife Sanctuary",
    "kolhapur": "Mahalaxmi Temple Kolhapur|Jyotiba Temple|Rankala Lake|Panhala Fort",
}

DESTINATION_SPOT_DATA.update(ADDITIONAL_SPIRITUAL_SPOT_DATA)
DESTINATION_SPOT_LIBRARY.update(
    {
        key: [item.strip() for item in value.split("|") if item.strip()]
        for key, value in ADDITIONAL_SPIRITUAL_SPOT_DATA.items()
    }
)

PLACE_KEY_ALIASES.update(
    {
        "allahabad": "prayagraj",
        "bodhgaya": "bodh gaya",
        "vaishno devi katra": "vaishno devi",
        "kedarnath temple": "kedarnath",
        "badrinath temple": "badrinath",
        "hemkunt sahib": "hemkund sahib",
        "tiruvannamalai": "thiruvannamalai",
        "omkareshwar jyotirlinga": "omkareshwar",
    }
)

CITY_COORDINATES = {
    "agra": (27.1767, 78.0081),
    "ahmedabad": (23.0225, 72.5714),
    "ajmer": (26.4499, 74.6399),
    "alappuzha": (9.4981, 76.3388),
    "alibaug": (18.6414, 72.8722),
    "alleppey": (9.4981, 76.3388),
    "amritsar": (31.6340, 74.8723),
    "auli": (30.5284, 79.5669),
    "aurangabad": (19.8762, 75.3433),
    "ayodhya": (26.7922, 82.1998),
    "badami": (15.9149, 75.6768),
    "bandhavgarh": (23.7220, 81.0187),
    "bengaluru": (12.9716, 77.5946),
    "bhopal": (23.2599, 77.4126),
    "bhubaneswar": (20.2961, 85.8245),
    "bikaner": (28.0229, 73.3119),
    "chandigarh": (30.7333, 76.7794),
    "chennai": (13.0827, 80.2707),
    "cherrapunji": (25.2702, 91.7326),
    "coimbatore": (11.0168, 76.9558),
    "coorg": (12.3375, 75.8069),
    "dalhousie": (32.5387, 75.9701),
    "daman": (20.3974, 72.8328),
    "darjeeling": (27.0410, 88.2663),
    "dehradun": (30.3165, 78.0322),
    "delhi": (28.6139, 77.2090),
    "dharamshala": (32.2190, 76.3234),
    "digha": (21.6270, 87.5030),
    "diu": (20.7144, 70.9876),
    "dwarka": (22.2442, 68.9685),
    "gangtok": (27.3389, 88.6065),
    "goa": (15.2993, 74.1240),
    "gokarna": (14.5500, 74.3188),
    "gulmarg": (34.0484, 74.3805),
    "guwahati": (26.1445, 91.7362),
    "gwalior": (26.2183, 78.1828),
    "hampi": (15.3350, 76.4600),
    "haridwar": (29.9457, 78.1642),
    "havelock island": (11.9870, 92.9826),
    "hyderabad": (17.3850, 78.4867),
    "indore": (22.7196, 75.8577),
    "itanagar": (27.0844, 93.6053),
    "jabalpur": (23.1815, 79.9864),
    "jaipur": (26.9124, 75.7873),
    "jaisalmer": (26.9157, 70.9083),
    "jodhpur": (26.2389, 73.0243),
    "kanchipuram": (12.8342, 79.7036),
    "kanha": (22.3344, 80.6115),
    "kannur": (11.8745, 75.3704),
    "kanpur": (26.4499, 80.3319),
    "kanyakumari": (8.0883, 77.5385),
    "kasol": (32.0094, 77.3145),
    "katra": (32.9916, 74.9318),
    "kaziranga": (26.5775, 93.1711),
    "khajuraho": (24.8318, 79.9199),
    "kochi": (9.9312, 76.2673),
    "kodaikanal": (10.2381, 77.4892),
    "kohima": (25.6701, 94.1077),
    "kolkata": (22.5726, 88.3639),
    "kovalam": (8.3988, 76.9782),
    "kullu": (31.9579, 77.1095),
    "kumarakom": (9.6175, 76.4319),
    "lakshadweep": (10.5667, 72.6417),
    "leh": (34.1526, 77.5771),
    "lonavala": (18.7546, 73.4062),
    "lucknow": (26.8467, 80.9462),
    "madurai": (9.9252, 78.1198),
    "mahabaleshwar": (17.9307, 73.6477),
    "manali": (32.2396, 77.1887),
    "mangalore": (12.9141, 74.8560),
    "mathura": (27.4924, 77.6737),
    "mount abu": (24.5926, 72.7156),
    "mumbai": (19.0760, 72.8777),
    "munnar": (10.0889, 77.0595),
    "mussoorie": (30.4598, 78.0644),
    "mysuru": (12.2958, 76.6394),
    "nainital": (29.3803, 79.4636),
    "nalanda": (25.1367, 85.4440),
    "nashik": (19.9975, 73.7898),
    "neemrana": (27.9880, 76.3844),
    "new delhi": (28.6139, 77.2090),
    "nubra valley": (34.6074, 77.5594),
    "ooty": (11.4102, 76.6950),
    "orchha": (25.3510, 78.6400),
    "patna": (25.5941, 85.1376),
    "pelling": (27.2996, 88.2350),
    "pondicherry": (11.9416, 79.8083),
    "port blair": (11.6234, 92.7265),
    "puducherry": (11.9416, 79.8083),
    "pune": (18.5204, 73.8567),
    "puri": (19.8135, 85.8312),
    "pushkar": (26.4898, 74.5511),
    "raipur": (21.2514, 81.6296),
    "rameswaram": (9.2876, 79.3129),
    "ranchi": (23.3441, 85.3096),
    "ranikhet": (29.6434, 79.4322),
    "ranthambore": (26.0173, 76.5026),
    "rishikesh": (30.0869, 78.2676),
    "saputara": (20.5783, 73.7500),
    "shillong": (25.5788, 91.8933),
    "shimla": (31.1048, 77.1734),
    "shirdi": (19.7645, 74.4762),
    "somnath": (20.8880, 70.4012),
    "spiti": (32.2467, 78.0348),
    "srinagar": (34.0837, 74.7973),
    "surat": (21.1702, 72.8311),
    "tawang": (27.5864, 91.8650),
    "thanjavur": (10.7867, 79.1378),
    "thekkady": (9.6031, 77.1615),
    "thiruvananthapuram": (8.5241, 76.9366),
    "tirupati": (13.6288, 79.4192),
    "trivandrum": (8.5241, 76.9366),
    "udaipur": (24.5854, 73.7125),
    "ujjain": (23.1765, 75.7885),
    "vadodara": (22.3072, 73.1812),
    "varanasi": (25.3176, 82.9739),
    "varkala": (8.7379, 76.7163),
    "velankanni": (10.6833, 79.8529),
    "vijayawada": (16.5062, 80.6480),
    "visakhapatnam": (17.6868, 83.2185),
    "vrindavan": (27.5806, 77.7006),
    "wayanad": (11.6854, 76.1320),
    "yercaud": (11.7753, 78.2096),
    "ziro": (27.5883, 93.8285),
}

ADDITIONAL_SPIRITUAL_COORDINATES: dict[str, tuple[float, float]] = {
    "kedarnath": (30.7352, 79.0669),
    "badrinath": (30.7447, 79.4939),
    "gangotri": (30.9947, 78.9398),
    "yamunotri": (31.0136, 78.4602),
    "amarnath": (34.2146, 75.5010),
    "vaishno devi": (33.0308, 74.9496),
    "prayagraj": (25.4358, 81.8463),
    "bodh gaya": (24.6959, 84.9910),
    "gaya": (24.7955, 85.0002),
    "deoghar": (24.4829, 86.6947),
    "srisailam": (16.0727, 78.8686),
    "omkareshwar": (22.2452, 76.1467),
    "udupi": (13.3409, 74.7421),
    "guruvayur": (10.5943, 76.0411),
    "sabarimala": (9.4320, 77.0933),
    "palani": (10.4500, 77.5200),
    "thiruvannamalai": (12.2253, 79.0747),
    "chidambaram": (11.3996, 79.6936),
    "kumbakonam": (10.9601, 79.3845),
    "sringeri": (13.4197, 75.2526),
    "pandharpur": (17.6770, 75.3235),
    "nanded": (19.1383, 77.3210),
    "anandpur sahib": (31.2398, 76.5026),
    "hemkund sahib": (30.7260, 79.6044),
    "bhimashankar": (19.0714, 73.5337),
    "kolhapur": (16.7050, 74.2433),
}

CITY_COORDINATES.update(ADDITIONAL_SPIRITUAL_COORDINATES)

# Road distances in km for common pairs; treated as exact table values.
ROAD_DISTANCE_KM = {
    ("delhi", "goa"): 1882.0,
    ("delhi", "manali"): 536.0,
    ("delhi", "jaipur"): 281.0,
    ("delhi", "agra"): 233.0,
    ("mumbai", "goa"): 590.0,
    ("mumbai", "pune"): 148.0,
    ("bengaluru", "goa"): 560.0,
    ("chennai", "bengaluru"): 346.0,
    ("kolkata", "puri"): 499.0,
    ("chandigarh", "manali"): 293.0,
}

TRAIN_CLASS_LABELS = {
    "SL": "Sleeper",
    "3A": "AC 3 Tier",
    "2A": "AC 2 Tier",
    "1A": "AC First",
    "CC": "Chair Car",
    "EC": "Executive Chair Car",
    "2S": "Second Sitting",
}

TRAIN_ROUTE_LIBRARY: dict[tuple[str, str], list[dict[str, object]]] = {
    ("mumbai", "goa"): [
        {
            "name": "Mumbai Goa Vande Bharat",
            "number": "22229",
            "departure": "05:25",
            "arrival": "13:10",
            "duration": "7h 45m",
            "classes": {"CC": 1670, "EC": 2890},
        },
        {
            "name": "Konkan Kanya Express",
            "number": "20111",
            "departure": "23:05",
            "arrival": "10:45",
            "duration": "11h 40m",
            "classes": {"SL": 780, "3A": 2050, "2A": 2890},
        },
        {
            "name": "Matsyagandha Express",
            "number": "12619",
            "departure": "15:20",
            "arrival": "04:15",
            "duration": "12h 55m",
            "classes": {"SL": 760, "3A": 1980, "2A": 2810},
        },
    ],
    ("delhi", "jaipur"): [
        {
            "name": "Ajmer Shatabdi Express",
            "number": "12015",
            "departure": "06:05",
            "arrival": "10:45",
            "duration": "4h 40m",
            "classes": {"CC": 910, "EC": 1750},
        },
        {
            "name": "Delhi Jaipur Double Decker",
            "number": "12985",
            "departure": "07:20",
            "arrival": "11:40",
            "duration": "4h 20m",
            "classes": {"CC": 780},
        },
        {
            "name": "Mandor Express",
            "number": "12461",
            "departure": "21:20",
            "arrival": "05:30",
            "duration": "8h 10m",
            "classes": {"SL": 460, "3A": 1250, "2A": 1820},
        },
    ],
    ("delhi", "varanasi"): [
        {
            "name": "Vande Bharat Express",
            "number": "22436",
            "departure": "06:00",
            "arrival": "14:00",
            "duration": "8h 00m",
            "classes": {"CC": 1850, "EC": 3350},
        },
        {
            "name": "Shiv Ganga Express",
            "number": "12560",
            "departure": "20:05",
            "arrival": "08:10",
            "duration": "12h 05m",
            "classes": {"SL": 690, "3A": 1840, "2A": 2650},
        },
        {
            "name": "Kashi Vishwanath Express",
            "number": "15128",
            "departure": "11:25",
            "arrival": "00:20",
            "duration": "12h 55m",
            "classes": {"SL": 720, "3A": 1920, "2A": 2780},
        },
    ],
    ("delhi", "kolkata"): [
        {
            "name": "Howrah Rajdhani Express",
            "number": "12302",
            "departure": "16:55",
            "arrival": "10:05",
            "duration": "17h 10m",
            "classes": {"3A": 3200, "2A": 4450, "1A": 7200},
        },
        {
            "name": "Howrah Duronto Express",
            "number": "12274",
            "departure": "12:55",
            "arrival": "06:10",
            "duration": "17h 15m",
            "classes": {"3A": 3050, "2A": 4250},
        },
        {
            "name": "Poorva Express",
            "number": "12304",
            "departure": "17:40",
            "arrival": "13:45",
            "duration": "20h 05m",
            "classes": {"SL": 890, "3A": 2390, "2A": 3380},
        },
    ],
    ("chennai", "bengaluru"): [
        {
            "name": "Shatabdi Express",
            "number": "12027",
            "departure": "06:00",
            "arrival": "10:55",
            "duration": "4h 55m",
            "classes": {"CC": 980, "EC": 1880},
        },
        {
            "name": "Brindavan Express",
            "number": "12639",
            "departure": "07:35",
            "arrival": "13:20",
            "duration": "5h 45m",
            "classes": {"2S": 180, "CC": 760},
        },
        {
            "name": "Lalbagh Express",
            "number": "12607",
            "departure": "15:35",
            "arrival": "21:20",
            "duration": "5h 45m",
            "classes": {"2S": 190, "CC": 790},
        },
    ],
    ("kolkata", "puri"): [
        {
            "name": "Dhauli Express",
            "number": "12821",
            "departure": "06:20",
            "arrival": "12:35",
            "duration": "6h 15m",
            "classes": {"2S": 220, "CC": 760},
        },
        {
            "name": "Puri Shatabdi Express",
            "number": "12277",
            "departure": "06:00",
            "arrival": "12:30",
            "duration": "6h 30m",
            "classes": {"CC": 980, "EC": 1840},
        },
        {
            "name": "Jagannath Express",
            "number": "18409",
            "departure": "19:35",
            "arrival": "04:30",
            "duration": "8h 55m",
            "classes": {"SL": 420, "3A": 1180, "2A": 1710},
        },
    ],
    ("bengaluru", "mysuru"): [
        {
            "name": "Mysuru Shatabdi",
            "number": "12007",
            "departure": "11:00",
            "arrival": "13:15",
            "duration": "2h 15m",
            "classes": {"CC": 520, "EC": 980},
        },
        {
            "name": "Kaveri Express",
            "number": "16021",
            "departure": "20:30",
            "arrival": "23:20",
            "duration": "2h 50m",
            "classes": {"2S": 120, "CC": 420},
        },
        {
            "name": "Chamundi Express",
            "number": "16215",
            "departure": "06:45",
            "arrival": "09:45",
            "duration": "3h 00m",
            "classes": {"2S": 110, "CC": 390},
        },
    ],
    ("mumbai", "delhi"): [
        {
            "name": "Mumbai Rajdhani Express",
            "number": "12951",
            "departure": "17:00",
            "arrival": "08:35",
            "duration": "15h 35m",
            "classes": {"3A": 2900, "2A": 4050, "1A": 6500},
        },
        {
            "name": "August Kranti Rajdhani",
            "number": "12953",
            "departure": "17:40",
            "arrival": "09:45",
            "duration": "16h 05m",
            "classes": {"SL": 780, "3A": 2160, "2A": 3140},
        },
        {
            "name": "Mumbai Garib Rath",
            "number": "12909",
            "departure": "16:35",
            "arrival": "08:10",
            "duration": "15h 35m",
            "classes": {"3A": 1670},
        },
    ],
    ("hyderabad", "goa"): [
        {
            "name": "Goa Express",
            "number": "12780",
            "departure": "15:10",
            "arrival": "06:40",
            "duration": "15h 30m",
            "classes": {"SL": 650, "3A": 1750, "2A": 2520},
        },
        {
            "name": "Vasco Express",
            "number": "17039",
            "departure": "18:00",
            "arrival": "08:30",
            "duration": "14h 30m",
            "classes": {"SL": 620, "3A": 1680, "2A": 2440},
        },
        {
            "name": "Konkan Link Express",
            "number": "17221",
            "departure": "11:50",
            "arrival": "03:20",
            "duration": "15h 30m",
            "classes": {"SL": 590, "3A": 1620},
        },
    ],
    ("mumbai", "udaipur"): [
        {
            "name": "Mewar Express",
            "number": "12963",
            "departure": "20:40",
            "arrival": "13:10",
            "duration": "16h 30m",
            "classes": {"SL": 670, "3A": 1800, "2A": 2620},
        },
        {
            "name": "Bandra Udaipur Express",
            "number": "12995",
            "departure": "17:10",
            "arrival": "09:55",
            "duration": "16h 45m",
            "classes": {"SL": 640, "3A": 1710, "2A": 2480},
        },
        {
            "name": "Udaipur Humsafar",
            "number": "22973",
            "departure": "22:15",
            "arrival": "14:35",
            "duration": "16h 20m",
            "classes": {"3A": 1950},
        },
    ],
}

SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

COUNTRY_CAPITALS = {
    "india": "New Delhi",
    "japan": "Tokyo",
    "france": "Paris",
    "germany": "Berlin",
    "italy": "Rome",
    "spain": "Madrid",
    "united kingdom": "London",
    "uk": "London",
    "united states": "Washington, D.C.",
    "usa": "Washington, D.C.",
    "canada": "Ottawa",
    "australia": "Canberra",
    "china": "Beijing",
    "russia": "Moscow",
    "brazil": "Brasilia",
    "uae": "Abu Dhabi",
    "singapore": "Singapore",
    "nepal": "Kathmandu",
    "bhutan": "Thimphu",
    "sri lanka": "Sri Jayawardenepura Kotte",
}

GENERAL_TOPIC_EXPLAINERS = {
    "photosynthesis": (
        "Photosynthesis is the process where green plants use sunlight, water, and carbon dioxide "
        "to produce glucose (food) and release oxygen."
    ),
    "artificial intelligence": (
        "Artificial Intelligence (AI) is the field of building systems that can perform tasks "
        "that usually require human intelligence, such as reasoning, language, and decision-making."
    ),
    "machine learning": (
        "Machine learning is a branch of AI where models learn patterns from data to make predictions "
        "or decisions without being explicitly programmed for every case."
    ),
    "blockchain": (
        "Blockchain is a distributed digital ledger where transactions are recorded in linked blocks, "
        "making records transparent and hard to tamper with."
    ),
    "quantum computing": (
        "Quantum computing uses qubits and quantum effects like superposition to solve specific "
        "problems much faster than classical computers."
    ),
    "internet": (
        "The internet is a global network of connected computers that communicate using standardized "
        "protocols to share information and services."
    ),
    "cloud computing": (
        "Cloud computing is the delivery of computing services such as servers, storage, and databases "
        "over the internet instead of local infrastructure."
    ),
    "api": (
        "An API (Application Programming Interface) is a defined way for software systems to communicate "
        "and exchange data or functionality."
    ),
    "python": (
        "Python is a high-level programming language known for readability, rapid development, and "
        "strong libraries for web, data science, and automation."
    ),
    "flask": (
        "Flask is a lightweight Python web framework used to build web applications and APIs quickly."
    ),
    "html": (
        "HTML (HyperText Markup Language) structures content on web pages using elements like headings, "
        "paragraphs, forms, and links."
    ),
    "css": (
        "CSS (Cascading Style Sheets) controls the presentation of web pages including layout, colors, "
        "fonts, and responsive design."
    ),
    "javascript": (
        "JavaScript is a programming language used to make web pages interactive and dynamic in browsers."
    ),
    "database": (
        "A database is an organized system for storing, retrieving, and managing data efficiently."
    ),
    "gravity": (
        "Gravity is the force of attraction between masses; on Earth, it pulls objects toward the center "
        "of the planet."
    ),
    "inflation": (
        "Inflation is the rise in general price levels over time, which reduces purchasing power."
    ),
    "climate change": (
        "Climate change refers to long-term shifts in global temperature and weather patterns, largely driven "
        "by greenhouse gas emissions."
    ),
    "solar system": (
        "The solar system consists of the Sun and all objects gravitationally bound to it, including planets, "
        "moons, asteroids, and comets."
    ),
}

INDIA_WANDER_PLACES = [
    "Agra",
    "Ahmedabad",
    "Ajmer",
    "Alappuzha",
    "Alibaug",
    "Alleppey",
    "Amarnath",
    "Amritsar",
    "Anandpur Sahib",
    "Auli",
    "Aurangabad",
    "Ayodhya",
    "Badami",
    "Badrinath",
    "Bandhavgarh",
    "Bengaluru",
    "Bhimashankar",
    "Bhopal",
    "Bhubaneswar",
    "Bikaner",
    "Bodh Gaya",
    "Chandigarh",
    "Chennai",
    "Cherrapunji",
    "Chidambaram",
    "Coimbatore",
    "Coorg",
    "Dalhousie",
    "Daman",
    "Darjeeling",
    "Dehradun",
    "Delhi",
    "Deoghar",
    "Dharamshala",
    "Digha",
    "Diu",
    "Dwarka",
    "Gangotri",
    "Gangtok",
    "Gaya",
    "Goa",
    "Gokarna",
    "Gulmarg",
    "Guruvayur",
    "Guwahati",
    "Gwalior",
    "Hampi",
    "Haridwar",
    "Havelock Island",
    "Hemkund Sahib",
    "Hyderabad",
    "Indore",
    "Itanagar",
    "Jabalpur",
    "Jaipur",
    "Jaisalmer",
    "Jodhpur",
    "Kanchipuram",
    "Kanha",
    "Kannur",
    "Kanpur",
    "Kanyakumari",
    "Kasol",
    "Katra",
    "Kaziranga",
    "Kedarnath",
    "Khajuraho",
    "Kochi",
    "Kodaikanal",
    "Kohima",
    "Kolhapur",
    "Kolkata",
    "Kovalam",
    "Kullu",
    "Kumarakom",
    "Kumbakonam",
    "Lakshadweep",
    "Leh",
    "Lonavala",
    "Lucknow",
    "Madurai",
    "Mahabaleshwar",
    "Manali",
    "Mangalore",
    "Mathura",
    "Mount Abu",
    "Mumbai",
    "Munnar",
    "Mussoorie",
    "Mysuru",
    "Nainital",
    "Nalanda",
    "Nanded",
    "Nashik",
    "Neemrana",
    "New Delhi",
    "Nubra Valley",
    "Omkareshwar",
    "Ooty",
    "Orchha",
    "Palani",
    "Pandharpur",
    "Patna",
    "Pelling",
    "Pondicherry",
    "Port Blair",
    "Prayagraj",
    "Puducherry",
    "Pune",
    "Puri",
    "Pushkar",
    "Raipur",
    "Rameswaram",
    "Ranchi",
    "Ranikhet",
    "Ranthambore",
    "Rishikesh",
    "Sabarimala",
    "Saputara",
    "Shillong",
    "Shimla",
    "Shirdi",
    "Somnath",
    "Spiti",
    "Srinagar",
    "Sringeri",
    "Srisailam",
    "Surat",
    "Tawang",
    "Thanjavur",
    "Thekkady",
    "Thiruvananthapuram",
    "Thiruvannamalai",
    "Tirupati",
    "Trivandrum",
    "Udaipur",
    "Udupi",
    "Ujjain",
    "Vadodara",
    "Vaishno Devi",
    "Varanasi",
    "Varkala",
    "Velankanni",
    "Vijayawada",
    "Visakhapatnam",
    "Vrindavan",
    "Wayanad",
    "Yamunotri",
    "Yercaud",
    "Ziro",
]

KNOWN_PLACE_DISPLAY: dict[str, str] = {}
for _place in INDIA_WANDER_PLACES:
    KNOWN_PLACE_DISPLAY[re.sub(r"\s+", " ", _place.strip().lower())] = _place
for _place in DESTINATION_PROFILES:
    KNOWN_PLACE_DISPLAY.setdefault(_place, _place.title())
for _place in DESTINATION_SPOT_LIBRARY:
    KNOWN_PLACE_DISPLAY.setdefault(_place, _place.title())
for _alias, _target in PLACE_KEY_ALIASES.items():
    KNOWN_PLACE_DISPLAY.setdefault(_alias, KNOWN_PLACE_DISPLAY.get(_target, _target.title()))

HOTEL_CONTACT_BOOK: dict[str, dict[str, str]] = {
    "calangute-seabreeze-resort": {
        "phone": "+91-98765-41001",
        "email": "booking@calanguteseabreeze.com",
        "address": "Beach Road, Calangute, Goa",
    },
    "panjim-riverside-hotel": {
        "phone": "+91-98765-41002",
        "email": "stay@panjimriverside.in",
        "address": "Mandovi Riverside, Panaji, Goa",
    },
    "candolim-bay-retreat": {
        "phone": "+91-98765-41003",
        "email": "frontdesk@candolimbayretreat.com",
        "address": "Candolim Coastline, Goa",
    },
    "anjuna-palm-residency": {
        "phone": "+91-98765-41004",
        "email": "hello@anjunapalmstay.in",
        "address": "North Anjuna, Goa",
    },
    "benaulim-dunes-stay": {
        "phone": "+91-98765-41005",
        "email": "bookings@benaulimdunes.com",
        "address": "Benaulim Main Road, South Goa",
    },
    "snowline-view-resort": {
        "phone": "+91-98765-42001",
        "email": "book@snowlineviewmanali.com",
        "address": "Mall Road Extension, Manali",
    },
    "beas-river-retreat": {
        "phone": "+91-98765-42002",
        "email": "stay@beasretreat.in",
        "address": "Beas Riverside, Vashisht Road, Manali",
    },
    "pine-crest-manali": {
        "phone": "+91-98765-42003",
        "email": "reservations@pinecrestmanali.com",
        "address": "Old Manali Pine Belt",
    },
    "solang-meadow-stay": {
        "phone": "+91-98765-42004",
        "email": "contact@solangmeadow.in",
        "address": "Solang Valley Route, Manali",
    },
    "himalayan-nest-hotel": {
        "phone": "+91-98765-42005",
        "email": "desk@himalayannest.in",
        "address": "Prini Link Road, Manali",
    },
    "pink-city-palace-view": {
        "phone": "+91-98765-43001",
        "email": "book@pinkcitypalaceview.com",
        "address": "Bani Park Circle, Jaipur",
    },
    "amber-heritage-inn": {
        "phone": "+91-98765-43002",
        "email": "frontoffice@amberheritageinn.in",
        "address": "Amer Road, Jaipur",
    },
    "raj-mahal-courtyard": {
        "phone": "+91-98765-43003",
        "email": "stay@rajmahalcourtyard.com",
        "address": "Civil Lines, Jaipur",
    },
    "hawa-mahal-residency": {
        "phone": "+91-98765-43004",
        "email": "booking@hawamahalresidency.in",
        "address": "MI Road, Jaipur",
    },
    "nahargarh-heights-stay": {
        "phone": "+91-98765-43005",
        "email": "hello@nahargarhheights.com",
        "address": "Shastri Nagar, Jaipur",
    },
}

HOTEL_REVIEW_BOOK: dict[str, list[dict[str, str | int]]] = {
    "calangute-seabreeze-resort": [
        {"name": "Rohan", "rating": 5, "comment": "Very close to beach and clean rooms."},
        {"name": "Aditi", "rating": 4, "comment": "Great breakfast and quick check-in."},
        {"name": "Nikhil", "rating": 4, "comment": "Good value for group stay."},
    ],
    "pine-crest-manali": [
        {"name": "Sneha", "rating": 5, "comment": "Amazing mountain view from balcony."},
        {"name": "Vivek", "rating": 4, "comment": "Good staff support for local tours."},
        {"name": "Arjun", "rating": 4, "comment": "Comfortable rooms in Old Manali area."},
    ],
    "raj-mahal-courtyard": [
        {"name": "Kavya", "rating": 5, "comment": "Heritage feel and top dining experience."},
        {"name": "Harsh", "rating": 4, "comment": "Nice location for city sightseeing."},
        {"name": "Pranav", "rating": 4, "comment": "Service quality was very good."},
    ],
}


def normalize_place(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def resolve_place_key(value: str) -> str:
    normalized = normalize_place(value)
    return PLACE_KEY_ALIASES.get(normalized, normalized)


def display_place_name(place_key: str) -> str:
    return KNOWN_PLACE_DISPLAY.get(place_key, place_key.title())


def detect_known_place_key(text: str) -> str | None:
    lowered = normalize_place(text)
    for place_key in sorted(KNOWN_PLACE_DISPLAY.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(place_key)}\b", lowered):
            return place_key
    return None


def resolve_active_place(message: str, context: dict[str, object], fallback_destination: str) -> tuple[str, bool]:
    lower = message.lower()
    mentioned_key = detect_known_place_key(message)
    visited_context = str(context.get("visited_place", "")).strip()
    visited_mode = any(
        phrase in lower
        for phrase in [
            "visited place",
            "i visited",
            "we visited",
            "already visited",
            "place i visited",
        ]
    )

    if visited_mode:
        if mentioned_key:
            return display_place_name(mentioned_key), True
        if visited_context:
            return visited_context, True
        return fallback_destination, True

    if mentioned_key:
        return display_place_name(mentioned_key), False
    return fallback_destination, False


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return re.sub(r"-+", "-", slug).strip("-")


def default_hotel_contact(hotel_name: str, destination: str, area: str) -> dict[str, str]:
    random_seed = time.time_ns() ^ sum(ord(char) for char in f"{hotel_name}|{destination}|{area}")
    rng = random.Random(random_seed)
    domain = slugify(f"{hotel_name}-{destination}")[:24] or "grouptravelstay"
    inbox = rng.choice(["reservations", "frontdesk", "stays", "contact"])
    phone = f"+91-{rng.randint(62000, 99999)}{rng.randint(10000, 99999)}"
    return {
        "phone": phone,
        "email": f"{inbox}@{domain}.com",
        "address": f"{area}, {destination.title()}, India",
    }


def default_hotel_reviews(hotel_name: str, destination: str) -> list[dict[str, str | int]]:
    return [
        {"name": "Traveler A", "rating": 4, "comment": f"Good stay experience at {hotel_name} in {destination.title()}."},
        {"name": "Traveler B", "rating": 4, "comment": "Clean rooms and cooperative staff."},
        {"name": "Traveler C", "rating": 5, "comment": "Great location for sightseeing and food access."},
    ]


def default_hotel_booking_url(hotel_name: str, destination: str) -> str:
    query = urlparse.quote_plus(f"{hotel_name} {destination} hotel booking")
    return f"https://www.google.com/travel/hotels?q={query}"


def google_place_photo_url(photo_name: str, max_width: int = 1200) -> str:
    clean_name = str(photo_name).strip()
    if not clean_name or not GOOGLE_MAPS_API_KEY:
        return ""
    encoded_name = urlparse.quote(clean_name, safe="/")
    return (
        f"https://places.googleapis.com/v1/{encoded_name}/media"
        f"?maxWidthPx={max(400, max_width)}&key={urlparse.quote(GOOGLE_MAPS_API_KEY)}"
    )


def _hotel_image_lock(hotel_name: str, destination: str, area: str) -> int:
    seed_text = f"{normalize_place(destination)}|{normalize_place(area)}|{normalize_place(hotel_name)}"
    seed = sum(ord(char) for char in seed_text)
    return max(1, seed % 10000)


def _hotel_image_catalog() -> list[str]:
    # Keep only hotel-focused tags (rooms/building/lobby). No generic nature tags.
    return [
        "hotel,room,interior,suite",
        "hotel,bedroom,interior,luxury",
        "hotel,building,facade,exterior",
        "hotel,lobby,interior,modern",
    ]


def default_hotel_image_url(
    hotel_name: str,
    destination: str,
    area: str,
    lat: float | None = None,
    lng: float | None = None,
) -> str:
    lock = _hotel_image_lock(hotel_name, destination, area)
    catalog = _hotel_image_catalog()
    image_tag = catalog[lock % len(catalog)]
    return f"https://loremflickr.com/900/600/{image_tag}?lock={lock}"



def enrich_hotel_record(hotel: dict[str, str | int], destination: str) -> dict[str, str | int | list[dict[str, str | int]]]:
    record: dict[str, str | int | list[dict[str, str | int]]] = deepcopy(hotel)
    name = str(record.get("name", "Hotel Stay"))
    area = str(record.get("area", "City Center"))
    record["slug"] = slugify(name)
    contact = HOTEL_CONTACT_BOOK.get(record["slug"], default_hotel_contact(name, destination, area))
    contact_phone = str(record.get("contact_phone", "")).strip() or contact["phone"]
    contact_email = str(record.get("contact_email", "")).strip() or contact["email"]
    address = str(record.get("address", "")).strip() or contact["address"]
    record["contact_phone"] = contact_phone
    record["contact_email"] = contact_email
    record["address"] = address
    existing_reviews = record.get("reviews")
    if isinstance(existing_reviews, list) and existing_reviews:
        record["reviews"] = existing_reviews
    else:
        record["reviews"] = HOTEL_REVIEW_BOOK.get(record["slug"], default_hotel_reviews(name, destination))
    booking_url = str(record.get("booking_url", "")).strip()
    if not booking_url.startswith(("http://", "https://")):
        booking_url = default_hotel_booking_url(name, destination)
    record["booking_url"] = booking_url
    website = str(record.get("website", "")).strip()
    if website and not website.startswith(("http://", "https://")):
        website = f"https://{website}"
    record["website"] = website
    map_url = str(record.get("map_url", "")).strip()
    record["map_url"] = map_url
    source = str(record.get("source", "")).strip() or "local-recommendation"
    record["source"] = source

    lat = _parse_numeric_value(record.get("lat"))
    lng = _parse_numeric_value(record.get("lng"))
    image_url = str(record.get("image_url", "")).strip()
    if not image_url:
        image_url = default_hotel_image_url(name, destination, area, lat=lat, lng=lng)
    record["image_url"] = image_url

    return record


def pair_key(start: str, destination: str) -> tuple[str, str]:
    a = normalize_place(start)
    b = normalize_place(destination)
    return (a, b) if a <= b else (b, a)


def _to_int(value: object, default: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _first_non_empty_text(candidates: list[object], default: str = "") -> str:
    for candidate in candidates:
        if isinstance(candidate, str):
            value = candidate.strip()
            if value:
                return value
    return default


def _parse_numeric_value(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def _collect_numeric_candidates(payload: object, tokens: tuple[str, ...], max_nodes: int = 300) -> list[float]:
    values: list[float] = []
    stack: list[tuple[str, object, int]] = [("", payload, 0)]
    visited = 0
    while stack and visited < max_nodes:
        path, node, depth = stack.pop()
        visited += 1
        if isinstance(node, dict) and depth < 4:
            for key, item in node.items():
                child_path = f"{path}.{str(key).lower()}" if path else str(key).lower()
                stack.append((child_path, item, depth + 1))
            continue
        if isinstance(node, list) and depth < 4:
            for item in node[:12]:
                stack.append((path, item, depth + 1))
            continue

        numeric = _parse_numeric_value(node)
        if numeric is None:
            continue
        if any(token in path for token in tokens):
            values.append(numeric)
    return values


def _first_http_url(payload: object, tokens: tuple[str, ...], max_nodes: int = 200) -> str:
    stack: list[tuple[str, object, int]] = [("", payload, 0)]
    visited = 0
    while stack and visited < max_nodes:
        path, node, depth = stack.pop()
        visited += 1
        if isinstance(node, dict) and depth < 4:
            for key, item in node.items():
                child_path = f"{path}.{str(key).lower()}" if path else str(key).lower()
                stack.append((child_path, item, depth + 1))
            continue
        if isinstance(node, list) and depth < 4:
            for item in node[:12]:
                stack.append((path, item, depth + 1))
            continue
        if isinstance(node, str) and node.startswith(("http://", "https://")) and any(token in path for token in tokens):
            return node
    return ""


def _looks_like_hotel_item(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    hotel_keys = {"name", "hotel_name", "property_name", "title", "price", "rate", "stars", "rating"}
    return bool(hotel_keys.intersection(set(item.keys())))


def _extract_hotel_items(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if _looks_like_hotel_item(item)]

    if not isinstance(payload, dict):
        return []

    stack: list[object] = [payload]
    visited = 0
    while stack and visited < 120:
        node = stack.pop()
        visited += 1
        if isinstance(node, list):
            matches = [item for item in node if _looks_like_hotel_item(item)]
            if matches:
                return matches
            for item in node[:20]:
                if isinstance(item, (dict, list)):
                    stack.append(item)
            continue
        if isinstance(node, dict):
            for item in node.values():
                if isinstance(item, (dict, list)):
                    stack.append(item)
    return []


def _post_json_payload(
    url: str, body: dict[str, object], headers: dict[str, str] | None = None, timeout_sec: int = 8
) -> object | None:
    request_headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    try:
        req = urlrequest.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=request_headers,
        )
        with urlrequest.urlopen(req, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _normalized_name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _estimate_price_from_level(level: int | None, target_price: int) -> int:
    if level is None:
        return target_price
    level = max(0, min(4, level))
    if level <= 1:
        return max(1800, target_price - 1200)
    if level == 2:
        return target_price
    if level == 3:
        return target_price + 1600
    return target_price + 3200


def fetch_google_famous_spots(destination: str, limit: int = 6) -> list[str]:
    global FAMOUS_SPOTS_DISABLED_UNTIL

    destination_name = destination.strip()
    if not destination_name or not GOOGLE_MAPS_API_KEY:
        return []

    limit = max(4, limit)
    now = time.time()
    cache_key = normalize_place(destination_name)
    cached = FAMOUS_SPOTS_CACHE.get(cache_key)
    if cached and now - cached[0] <= FAMOUS_SPOTS_CACHE_TTL_SEC:
        return cached[1][:limit]

    if now < FAMOUS_SPOTS_DISABLED_UNTIL:
        return []

    common_headers = {
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.types",
    }
    queries = [
        f"Top tourist attractions in {destination_name}",
        f"Must visit places in {destination_name}",
        f"Famous sightseeing spots in {destination_name}",
    ]
    tourist_types = {
        "tourist_attraction",
        "point_of_interest",
        "museum",
        "monument",
        "hindu_temple",
        "church",
        "mosque",
        "park",
        "natural_feature",
        "historical_landmark",
        "place_of_worship",
    }

    spots: list[str] = []
    seen: set[str] = set()
    had_response = False
    for query in queries:
        payload = _post_json_payload(
            "https://places.googleapis.com/v1/places:searchText",
            {"textQuery": query, "maxResultCount": max(10, limit * 2)},
            headers=common_headers,
        )
        if not isinstance(payload, dict):
            continue
        had_response = True
        places = payload.get("places", [])
        if not isinstance(places, list):
            continue

        for place in places:
            if not isinstance(place, dict):
                continue
            display_name = place.get("displayName", {})
            spot_name = display_name.get("text") if isinstance(display_name, dict) else place.get("name")
            name = _first_non_empty_text([spot_name], default="")
            if not name:
                continue

            place_types = place.get("types", [])
            if isinstance(place_types, list) and place_types:
                type_set = {str(item).lower() for item in place_types}
                if not type_set.intersection(tourist_types):
                    continue

            rating = _parse_numeric_value(place.get("rating"))
            if rating is not None and rating < 3.3:
                continue

            name_key = _normalized_name_key(name)
            if not name_key or name_key in seen:
                continue
            seen.add(name_key)
            spots.append(name)
            if len(spots) >= limit:
                break

        if len(spots) >= limit:
            break

    if not spots:
        if not had_response:
            FAMOUS_SPOTS_DISABLED_UNTIL = now + FAMOUS_SPOTS_RETRY_AFTER_SEC
        return []

    FAMOUS_SPOTS_CACHE[cache_key] = (now, spots)
    FAMOUS_SPOTS_DISABLED_UNTIL = 0.0
    return spots[:limit]


def get_destination_famous_spots(
    destination: str, profile: dict[str, object] | None = None, limit: int = 6
) -> tuple[list[str], str]:
    limit = max(4, limit)
    resolved_profile = profile if profile is not None else get_destination_profile(destination)
    local_raw = resolved_profile.get("attractions", [])
    local_spots = [str(item).strip() for item in local_raw if isinstance(item, str) and str(item).strip()]
    google_spots = fetch_google_famous_spots(destination, limit=limit)

    merged: list[str] = []
    seen: set[str] = set()
    for item in google_spots + local_spots:
        key = _normalized_name_key(item)
        if not key or key in seen:
            continue
        merged.append(item)
        seen.add(key)
        if len(merged) >= limit:
            break

    if not merged:
        merged = [
            f"{destination.title()} city heritage zone",
            f"{destination.title()} landmark viewpoint",
            f"{destination.title()} local cultural center",
            f"{destination.title()} riverside or beach stretch",
        ]

    while len(merged) < 4:
        merged.append(merged[len(merged) % len(merged)])

    source = "google-places" if google_spots else "destination-profile"
    return merged[:limit], source


def fetch_live_nearby_hotels(destination: str, budget: int, limit: int | None = 3) -> list[dict[str, str | int | float]]:
    destination_name = destination.strip()
    if not destination_name or not GOOGLE_MAPS_API_KEY:
        return []

    result_limit = 8 if limit is None else max(3, min(limit * 2, 12))
    target_price = max(2500, budget // 6)
    common_headers = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY}
    search_text_mask = "places.location,places.displayName,places.formattedAddress"
    search_text_payload = _post_json_payload(
        "https://places.googleapis.com/v1/places:searchText",
        {"textQuery": destination_name, "maxResultCount": 1},
        headers={**common_headers, "X-Goog-FieldMask": search_text_mask},
    )
    if not isinstance(search_text_payload, dict):
        return []
    center_places = search_text_payload.get("places", [])
    if not isinstance(center_places, list) or not center_places:
        return []

    center_location = center_places[0].get("location", {})
    lat = _parse_numeric_value(center_location.get("latitude"))
    lng = _parse_numeric_value(center_location.get("longitude"))
    if lat is None or lng is None:
        return []

    nearby_field_mask = ",".join(
        [
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.shortFormattedAddress",
            "places.location",
            "places.rating",
            "places.priceLevel",
            "places.googleMapsUri",
            "places.websiteUri",
            "places.nationalPhoneNumber",
            "places.internationalPhoneNumber",
            "places.photos",
        ]
    )
    nearby_payload = _post_json_payload(
        "https://places.googleapis.com/v1/places:searchNearby",
        {
            "includedTypes": ["lodging"],
            "maxResultCount": result_limit,
            "locationRestriction": {
                "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 9000.0}
            },
        },
        headers={**common_headers, "X-Goog-FieldMask": nearby_field_mask},
    )
    if not isinstance(nearby_payload, dict):
        return []
    nearby_results = nearby_payload.get("places", [])
    if not isinstance(nearby_results, list) or not nearby_results:
        return []

    price_lookup: dict[str, int] = {}

    hotels: list[dict[str, str | int | float]] = []
    seen_keys: set[str] = set()
    for place in nearby_results[:result_limit]:
        if not isinstance(place, dict):
            continue

        display_name = place.get("displayName", {})
        place_name = display_name.get("text") if isinstance(display_name, dict) else place.get("name")
        name = _first_non_empty_text([place_name], default="")
        if not name:
            continue
        name_key = _normalized_name_key(name)
        if not name_key or name_key in seen_keys:
            continue

        place_location = place.get("location", {})
        hotel_lat = _parse_numeric_value(place_location.get("latitude"))
        hotel_lng = _parse_numeric_value(place_location.get("longitude"))

        rating_raw = (
            _parse_numeric_value(place.get("rating"))
            or 4.0
        )
        if rating_raw > 5:
            rating_raw = rating_raw / 2
        rating = max(1, min(5, int(round(rating_raw))))

        price_level_raw = place.get("priceLevel")
        if isinstance(price_level_raw, str):
            price_level_map = {
                "PRICE_LEVEL_FREE": 0,
                "PRICE_LEVEL_INEXPENSIVE": 1,
                "PRICE_LEVEL_MODERATE": 2,
                "PRICE_LEVEL_EXPENSIVE": 3,
                "PRICE_LEVEL_VERY_EXPENSIVE": 4,
            }
            price_level_value = price_level_map.get(price_level_raw, -1)
        else:
            price_level_value = _to_int(price_level_raw, -1)
        if price_level_value < 0:
            price_level_value = None

        matched_price = price_lookup.get(name_key)
        if matched_price is None:
            matched_price = _estimate_price_from_level(price_level_value, target_price)

        address = _first_non_empty_text(
            [place.get("formattedAddress"), place.get("shortFormattedAddress")],
            default=f"{destination_name.title()}",
        )
        phone = _first_non_empty_text(
            [place.get("nationalPhoneNumber"), place.get("internationalPhoneNumber")],
            default="Not publicly listed",
        )
        website = _first_non_empty_text([place.get("websiteUri")], default="")
        map_url = _first_non_empty_text([place.get("googleMapsUri")], default="")
        booking_url = _first_non_empty_text([map_url, website], default=default_hotel_booking_url(name, destination_name))

        photo_name = ""
        photos = place.get("photos", [])
        if isinstance(photos, list) and photos:
            first_photo = photos[0]
            if isinstance(first_photo, dict):
                photo_name = _first_non_empty_text([first_photo.get("name")], default="")
        image_url = google_place_photo_url(photo_name)

        if hotel_lat is None or hotel_lng is None:
            continue

        hotels.append(
            {
                "name": name,
                "area": address,
                "price": matched_price,
                "rating": rating,
                "contact_phone": phone,
                "contact_email": "Not publicly listed",
                "address": address,
                "website": website,
                "map_url": map_url,
                "booking_url": booking_url,
                "image_url": image_url,
                "lat": hotel_lat,
                "lng": hotel_lng,
                "source": "google-places-live",
            }
        )
        seen_keys.add(name_key)

    hotels.sort(key=lambda hotel: abs(_to_int(hotel.get("price"), target_price) - target_price))
    return hotels if limit is None else hotels[:limit]


def _extract_budget(message: str) -> int | None:
    cleaned = message.replace(",", "").lower()
    keyword_patterns = [
        r"(?:budget|under|upto|up to|around|approx(?:imately)?|max(?:imum)?|within)\s*(?:rs\.?|inr|rupees?)?\s*(\d{3,7})",
        r"(?:rs\.?|inr|rupees?)\s*(\d{3,7})",
        r"(\d{3,7})\s*(?:rs|inr|rupees?)",
    ]

    for pattern in keyword_patterns:
        match = re.search(pattern, cleaned)
        if match:
            return int(match.group(1))

    large_numbers = [int(value) for value in re.findall(r"\d{3,7}", cleaned)]
    if large_numbers:
        return max(large_numbers)

    raw_numbers = [int(value) for value in re.findall(r"\d+", cleaned)]
    if not raw_numbers:
        return None

    if len(raw_numbers) == 1:
        return raw_numbers[0] if raw_numbers[0] >= 1000 else None

    non_tiny = [value for value in raw_numbers if value >= 1000]
    if non_tiny:
        return max(non_tiny)

    return max(raw_numbers) if max(raw_numbers) >= 1000 else None

def display_name_from_login_id(login_id: str) -> str:
    identifier = login_id.strip()
    if "@" in identifier:
        identifier = identifier.split("@", 1)[0]
    return identifier[:24] or "Traveler"


def normalize_login_identifier(login_id: str) -> str:
    return login_id.strip().lower()


def validate_login_identifier(login_id: str) -> str | None:
    value = login_id.strip()
    if not value:
        return "Username or email is required."
    if "@" in value:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            return "Enter a valid email format."
        return None
    if not re.fullmatch(r"[A-Za-z0-9_ ]{3,30}", value):
        return "Username must be 3-30 chars (letters, numbers, underscore)."
    return None


def validate_password_strength(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"\d", password):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one special character."
    return None


def validate_login_form(payload: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    data = {"login_id": payload.get("login_id", "").strip(), "password": payload.get("password", "")}
    errors: dict[str, str] = {}

    login_error = validate_login_identifier(data["login_id"])
    if login_error:
        errors["login_id"] = login_error

    password_error = validate_password_strength(data["password"])
    if password_error:
        errors["password"] = password_error

    return data, errors


def _normalize_itinerary_label(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return fallback
    return cleaned


def _profile_text_items(profile: dict[str, object], key: str) -> list[str]:
    raw = profile.get(key, [])
    if not isinstance(raw, list):
        return []
    results: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        value = _normalize_itinerary_label(item, "")
        if value:
            results.append(value)
    return results


def _profile_activity_labels(profile: dict[str, object]) -> list[str]:
    raw = profile.get("activities", [])
    if not isinstance(raw, list):
        return []
    labels: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = _normalize_itinerary_label(str(item.get("name", "")).strip(), "")
            if name:
                labels.append(name)
    return labels


def _unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        key = _normalized_name_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(value)
    return results


def _pick_or(values: list[str], index: int, fallback: str) -> str:
    if values:
        return values[index % len(values)]
    return fallback


def _clean_itinerary_spot(value: str, fallback: str) -> str:
    cleaned = _normalize_itinerary_label(value, fallback)
    cleaned = re.sub(r"^\s*around\s+", "", cleaned, flags=re.IGNORECASE).strip(" ,.-")
    return cleaned or fallback


def _format_nearby_reference(primary_spot: str, nearby_spot: str) -> str:
    nearby = nearby_spot.strip()
    if not nearby:
        return "in the nearby local area"
    if _normalized_name_key(primary_spot) == _normalized_name_key(nearby):
        return "in the nearby local area"
    return f"around {nearby}"


def _destination_theme(destination: str, profile: dict[str, object], spots: list[str]) -> str:
    text_blob = " ".join(
        [
            destination.lower(),
            " ".join(_profile_text_items(profile, "attractions")).lower(),
            " ".join(_profile_text_items(profile, "nearby_spots")).lower(),
            " ".join(spots).lower(),
        ]
    )
    tokens = set(re.findall(r"[a-z]+", text_blob))

    def has_any_words(*words: str) -> bool:
        return any(word in tokens for word in words)

    def has_any_phrases(*phrases: str) -> bool:
        return any(phrase in text_blob for phrase in phrases)

    if has_any_words("beach", "island", "coast", "bay", "marine", "sea", "shore", "ocean"):
        return "coastal"
    if has_any_words("mountain", "valley", "hill", "snow", "himalaya", "peak", "ridge", "glacier"):
        return "mountain"
    if has_any_words("fort", "palace", "museum", "heritage", "monument", "castle") or has_any_phrases("old city"):
        return "heritage"
    if has_any_words("temple", "ghat", "ashram", "pilgrim", "spiritual", "church", "mosque", "dargah", "stupa"):
        return "spiritual"
    if has_any_words("wildlife", "sanctuary", "safari", "jungle", "reserve") or has_any_phrases("national park"):
        return "wildlife"
    return "city"


def build_itinerary(destination: str, budget: int) -> list[dict[str, str]]:
    destination_label = destination.strip() or "your destination"
    normalized_input = normalize_place(destination_label)
    destination_key = resolve_place_key(destination_label)
    destination_title = KNOWN_PLACE_DISPLAY.get(normalized_input) or (
        display_place_name(destination_key) if destination_key else destination_label.title()
    )
    profile = get_destination_profile(destination_label)

    famous_spots, _ = get_destination_famous_spots(destination_label, profile, limit=10)
    attractions = _profile_text_items(profile, "attractions")
    nearby_spots = _profile_text_items(profile, "nearby_spots")
    foods = _profile_text_items(profile, "foods")
    shopping = _profile_text_items(profile, "shopping")
    activities = _profile_activity_labels(profile)

    must_visit_pool = _unique_keep_order(
        [_clean_itinerary_spot(item, destination_title) for item in (famous_spots + attractions)]
    )
    nearby_pool = _unique_keep_order([_clean_itinerary_spot(item, destination_title) for item in nearby_spots])

    if not must_visit_pool:
        must_visit_pool = [
            f"{destination_title} main landmark",
            f"{destination_title} heritage zone",
            f"{destination_title} scenic viewpoint",
            f"{destination_title} cultural district",
        ]

    if not nearby_pool:
        nearby_pool = list(must_visit_pool)

    while len(must_visit_pool) < 5:
        must_visit_pool.append(must_visit_pool[len(must_visit_pool) % len(must_visit_pool)])

    while len(nearby_pool) < 5:
        nearby_pool.append(nearby_pool[len(nearby_pool) % len(nearby_pool)])

    nearby_ref = [_format_nearby_reference(must_visit_pool[i], nearby_pool[i]) for i in range(5)]

    food_one = _pick_or(foods, 0, f"Local cuisine trail in {destination_title}")
    food_two = _pick_or(foods, 1, food_one)
    shop_pick = _pick_or(shopping, 0, f"Main market of {destination_title}")
    activity_one = _pick_or(activities, 0, f"Guided exploration around {must_visit_pool[1]}")
    activity_two = _pick_or(activities, 1, activity_one)

    theme = _destination_theme(destination_title, profile, must_visit_pool)

    if theme == "coastal":
        day_items = [
            f"Arrive in {destination_title}, check in, and unwind with a sunset stop at {must_visit_pool[0]} followed by a relaxed walk {nearby_ref[0]}.",
            f"Continue your coastal circuit at {must_visit_pool[1]}, explore {nearby_ref[1]}, and include {activity_one}.",
            f"Spend the day around {must_visit_pool[2]} and {nearby_ref[2]}, then enjoy a local meal: {food_one}.",
            f"Wrap up with {must_visit_pool[3]}, visit {nearby_ref[3]}, shop at {shop_pick}, and optionally try {activity_two}.",
        ]
    elif theme == "mountain":
        day_items = [
            f"Arrive in {destination_title}, settle in, and ease into the trip with {must_visit_pool[0]} and a short walk {nearby_ref[0]}.",
            f"Start early for scenic views at {must_visit_pool[1]}, continue {nearby_ref[1]}, and stop for {food_one}.",
            f"Reserve this day for nature and soft adventure around {must_visit_pool[2]} with {activity_one}, then relax {nearby_ref[2]}.",
            f"Finish with {must_visit_pool[3]}, explore {nearby_ref[3]}, shop at {shop_pick}, and keep {activity_two} as an optional add-on.",
        ]
    elif theme == "heritage":
        day_items = [
            f"Arrive in {destination_title}, check in, and begin with a heritage orientation at {must_visit_pool[0]} plus a walk {nearby_ref[0]}.",
            f"Follow a history-focused route through {must_visit_pool[1]} and {nearby_ref[1]}, then try {food_one}.",
            f"Explore architecture and local culture at {must_visit_pool[2]}, add {activity_one}, and spend the evening {nearby_ref[2]}.",
            f"Conclude with {must_visit_pool[3]}, browse {shop_pick}, and end the day with optional {activity_two}.",
        ]
    elif theme == "spiritual":
        day_items = [
            f"Arrive in {destination_title}, check in, and begin with evening darshan at {must_visit_pool[0]} followed by a calm walk {nearby_ref[0]}.",
            f"Start your morning with visits to {must_visit_pool[1]} and {nearby_ref[1]}, then take a meal break at {food_one}.",
            f"Spend the day exploring spiritual and cultural landmarks around {must_visit_pool[2]}, include {activity_one}, and unwind {nearby_ref[2]}.",
            f"Complete your circuit at {must_visit_pool[3]}, visit {nearby_ref[3]}, shop at {shop_pick}, and optionally add {activity_two}.",
        ]
    elif theme == "wildlife":
        day_items = [
            f"Arrive in {destination_title}, settle in, and take an orientation round near {must_visit_pool[0]} and {nearby_ref[0]}.",
            f"Begin early for exploration at {must_visit_pool[1]} and continue {nearby_ref[1]}, then pause for {food_one}.",
            f"Plan this day around {must_visit_pool[2]} with {activity_one}, followed by a relaxed evening {nearby_ref[2]}.",
            f"Close the trip with {must_visit_pool[3]}, quick shopping at {shop_pick}, and optional {activity_two}.",
        ]
    else:
        day_items = [
            f"Arrive in {destination_title}, check in, and start with {must_visit_pool[0]} plus an evening walk {nearby_ref[0]}.",
            f"Cover city highlights at {must_visit_pool[1]} and {nearby_ref[1]}, then try {food_one}.",
            f"Explore {must_visit_pool[2]}, include {activity_one}, and spend the evening {nearby_ref[2]} with {food_two}.",
            f"Finish at {must_visit_pool[3]}, stop by {shop_pick}, and add {activity_two} if time allows.",
        ]

    if budget >= 60000:
        day_items[3] += " Premium add-on experiences can also be scheduled for the evening."

    return [{"day": index + 1, "title": day_items[index]} for index in range(4)]


def _spot_label(raw_text: str, fallback: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", raw_text)
    cleaned = re.sub(r"[^A-Za-z\s]", " ", cleaned)
    words = [word for word in cleaned.split() if len(word) > 2]
    if not words:
        return fallback
    stop_words = {
        "and",
        "with",
        "from",
        "near",
        "local",
        "city",
        "trail",
        "beach",
        "fort",
        "market",
        "viewpoint",
        "heritage",
        "tour",
        "walk",
    }
    meaningful = [word.title() for word in words if word.lower() not in stop_words]
    if not meaningful:
        meaningful = [words[0].title()]
    return " ".join(meaningful[:2]).strip() or fallback


def build_spot_based_hotels(destination: str, budget: int, profile: dict[str, object], limit: int | None) -> list[dict[str, str | int]]:
    destination_title = destination.strip().title() or "Destination"
    destination_key = _normalized_name_key(destination_title)

    attractions_raw = profile.get("attractions", [])
    nearby_raw = profile.get("nearby_spots", [])

    attractions = attractions_raw if isinstance(attractions_raw, list) else []
    nearby_spots = nearby_raw if isinstance(nearby_raw, list) else []

    famous_spots, _ = get_destination_famous_spots(destination_title, profile, limit=10)

    # Name hotels from nearby spots first, then famous spots/attractions.
    nearby_labels: list[str] = []
    for spot in nearby_spots:
        if isinstance(spot, str):
            nearby_labels.append(_spot_label(spot, destination_title))

    famous_labels: list[str] = []
    for spot in famous_spots:
        if isinstance(spot, str):
            famous_labels.append(_spot_label(spot, destination_title))
    for spot in attractions:
        if isinstance(spot, str):
            famous_labels.append(_spot_label(spot, destination_title))

    labels = _unique_keep_order([label for label in (nearby_labels + famous_labels) if label.strip()])
    if not labels:
        labels = [f"{destination_title} Core", f"{destination_title} Heritage", f"{destination_title} View"]

    area_labels = _unique_keep_order([label for label in nearby_labels if label.strip()])
    if not area_labels:
        area_labels = [f"{destination_title} Core", f"{destination_title} Riverside", f"{destination_title} Market"]

    target_price = max(2200, budget // 6)
    desired_count = max(4, (limit or 6))

    suffixes = [
        "Residency",
        "Retreat",
        "Suites",
        "Plaza",
        "Inn",
        "Heritage Hotel",
    ]
    price_offsets = [-1000, -300, 450, 1100, 1700, 2300]
    ratings = [4, 4, 5, 4, 3, 5]

    hotels: list[dict[str, str | int]] = []
    used_name_keys: set[str] = set()

    for idx in range(desired_count * 4):
        if len(hotels) >= desired_count:
            break

        base_label = labels[idx % len(labels)].strip()
        if not base_label:
            continue

        base_key = _normalized_name_key(base_label)
        if destination_key and destination_key not in base_key:
            name_root = f"{base_label} {destination_title}"
        else:
            name_root = base_label

        suffix = suffixes[idx % len(suffixes)]
        hotel_name = f"{name_root} {suffix}".strip()
        hotel_name_key = _normalized_name_key(hotel_name)
        if not hotel_name_key or hotel_name_key in used_name_keys:
            continue

        area_name = area_labels[idx % len(area_labels)]
        price = max(1800, target_price + price_offsets[idx % len(price_offsets)])
        rating = ratings[idx % len(ratings)]

        hotels.append(
            {
                "name": hotel_name,
                "price": price,
                "rating": rating,
                "area": area_name,
                "source": "destination-nearby-spot-based",
            }
        )
        used_name_keys.add(hotel_name_key)

    return hotels if limit is None else hotels[:limit]


def get_destination_profile(destination: str) -> dict[str, object]:
    destination_label = destination.strip()
    normalized_input = normalize_place(destination_label)
    key = resolve_place_key(destination_label)

    existing_profile = DESTINATION_PROFILES.get(key)
    if existing_profile:
        return existing_profile

    display_key = key or normalized_input
    destination_title = KNOWN_PLACE_DISPLAY.get(normalized_input) or (
        display_place_name(display_key) if display_key else (destination_label.title() or "Destination")
    )

    library_spots = DESTINATION_SPOT_LIBRARY.get(key, [])
    google_spots = fetch_google_famous_spots(destination_title, limit=8) if len(library_spots) < 4 else []

    attractions = _unique_keep_order(
        [
            _normalize_itinerary_label(item, "")
            for item in (library_spots + google_spots)
            if isinstance(item, str) and str(item).strip()
        ]
    )

    if not attractions:
        attractions = [
            f"{destination_title} main landmark",
            f"{destination_title} heritage zone",
            f"{destination_title} scenic viewpoint",
            f"{destination_title} cultural center",
        ]

    while len(attractions) < 4:
        attractions.append(attractions[len(attractions) % len(attractions)])

    nearby_spots = _unique_keep_order([f"Around {spot}" for spot in attractions[:5]])
    while len(nearby_spots) < 4:
        nearby_spots.append(f"Around {attractions[len(nearby_spots) % len(attractions)]}")

    theme = _destination_theme(
        destination_title,
        {"attractions": attractions, "nearby_spots": nearby_spots},
        attractions,
    )

    food_by_theme = {
        "coastal": [
            f"Fresh seafood platter near {attractions[0]}",
            f"Beachside cafe meal near {attractions[1]}",
            f"Regional sweet and snack trail in {destination_title}",
        ],
        "mountain": [
            f"Local mountain thali near {attractions[0]}",
            f"Cafe and bakery stop near {attractions[1]}",
            f"Regional hot beverages and desserts in {destination_title}",
        ],
        "heritage": [
            f"Traditional thali around {attractions[0]}",
            f"Street-food walk near {attractions[1]}",
            f"Classic dessert shops around old city of {destination_title}",
        ],
        "spiritual": [
            f"Sattvik meals around {attractions[0]}",
            f"Temple-street local snacks near {attractions[1]}",
            f"Regional sweet shops in {destination_title}",
        ],
        "wildlife": [
            f"Eco-lodge local meals near {attractions[0]}",
            f"Regional cuisine stop near {attractions[1]}",
            f"Tribal and local food tasting in {destination_title}",
        ],
        "city": [
            f"Popular local dishes around {attractions[0]}",
            f"Street-food lane near {attractions[1]}",
            f"Regional dessert and snack trail in {destination_title}",
        ],
    }

    shopping_by_theme = {
        "coastal": [
            f"Beach market souvenirs near {attractions[0]}",
            f"Local handicrafts near {attractions[1]}",
            f"Regional packaged foods and gifts in {destination_title}",
        ],
        "mountain": [
            f"Woolens and handmade goods near {attractions[0]}",
            f"Local organic products near {attractions[1]}",
            f"Regional craft stores in {destination_title}",
        ],
        "heritage": [
            f"Handcrafted artifacts near {attractions[0]}",
            f"Traditional textiles near {attractions[1]}",
            f"Local market lanes in {destination_title}",
        ],
        "spiritual": [
            f"Temple market items near {attractions[0]}",
            f"Local handcrafted souvenirs near {attractions[1]}",
            f"Traditional bazaars in {destination_title}",
        ],
        "wildlife": [
            f"Nature and eco souvenirs near {attractions[0]}",
            f"Tribal craft stores near {attractions[1]}",
            f"Regional market shopping in {destination_title}",
        ],
        "city": [
            f"City center shopping near {attractions[0]}",
            f"Local craft markets near {attractions[1]}",
            f"Regional specialty stores in {destination_title}",
        ],
    }

    foods = food_by_theme.get(theme, food_by_theme["city"])
    shopping = shopping_by_theme.get(theme, shopping_by_theme["city"])

    activities = [
        {"name": f"Guided visit of {attractions[0]}", "price": 900},
        {"name": f"Local sightseeing around {attractions[1]}", "price": 1200},
        {"name": f"Experience trail near {attractions[2]}", "price": 1600},
        {"name": f"Sunset and market circuit at {attractions[3]}", "price": 1000},
    ]

    base_price = 3200
    hotels: list[dict[str, object]] = []
    for index in range(4):
        spot_name = _spot_label(attractions[index], destination_title)
        hotels.append(
            {
                "name": f"{spot_name} {destination_title} Stay",
                "price": base_price + (index * 450),
                "rating": 4 if index % 2 == 0 else 5,
                "area": _spot_label(nearby_spots[index], destination_title),
            }
        )

    return {
        "best_months": "October to March",
        "history_note": f"{destination_title} has strong local heritage and is a popular Indian travel circuit.",
        "culture_note": f"Explore food, markets, and cultural landmarks around {destination_title} for a complete local experience.",
        "attractions": attractions[:6],
        "nearby_spots": nearby_spots[:6],
        "foods": foods,
        "shopping": shopping,
        "transport": [
            f"Local cabs and autos available across {destination_title}",
            f"Day-hire taxi for major sightseeing spots in {destination_title}",
            "Shared local transport for budget-friendly short routes",
        ],
        "activities": activities,
        "hotels": hotels,
    }


def get_destination_hotels(destination: str, budget: int, limit: int | None = 3) -> list[dict[str, str | int | list[dict[str, str | int]]]]:
    # Keep hotel recommendations concise: always return between 5 and 6 entries.
    effective_limit = 6 if limit is None else max(5, min(6, _to_int(limit, 6)))

    live_hotels = fetch_live_nearby_hotels(destination, budget, limit=effective_limit)
    if live_hotels:
        return [enrich_hotel_record(hotel, destination) for hotel in live_hotels[:effective_limit]]

    profile = get_destination_profile(destination)
    selected_hotels = build_spot_based_hotels(destination, budget, profile, limit=effective_limit)

    return [enrich_hotel_record(hotel, destination) for hotel in selected_hotels[:effective_limit]]


def build_hotel_map_markers(hotels: list[dict[str, object]]) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    for hotel in hotels:
        lat = _parse_numeric_value(hotel.get("lat"))
        lng = _parse_numeric_value(hotel.get("lng"))
        if lat is None or lng is None:
            continue
        markers.append(
            {
                "name": str(hotel.get("name", "Hotel")),
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "price": _to_int(hotel.get("price"), 0),
                "rating": _to_int(hotel.get("rating"), 0),
                "phone": str(hotel.get("contact_phone", "")),
                "address": str(hotel.get("address", "")),
                "booking_url": str(hotel.get("booking_url", "")),
            }
        )
    return markers


def find_hotel_by_slug(hotels: list[dict[str, str | int | list[dict[str, str | int]]]], hotel_slug: str):
    for hotel in hotels:
        if str(hotel.get("slug", "")) == hotel_slug:
            return hotel
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def fetch_osrm_distance_km(start: tuple[float, float], end: tuple[float, float]) -> float | None:
    try:
        lat1, lon1 = start
        lat2, lon2 = end
        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{lon1:.6f},{lat1:.6f};{lon2:.6f},{lat2:.6f}?overview=false"
        )
        with urlrequest.urlopen(url, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
        routes = payload.get("routes", [])
        if not routes:
            return None
        return round(float(routes[0]["distance"]) / 1000, 1)
    except (KeyError, ValueError, TypeError, urlerror.URLError, TimeoutError):
        return None


def compute_trip_distance(starting_point: str, destination: str, use_online: bool = True) -> dict[str, object]:
    start_label = starting_point.strip().title() or "Start"
    destination_label = destination.strip().title() or "Destination"
    start_key = normalize_place(starting_point)
    destination_key = normalize_place(destination)
    start_coords = CITY_COORDINATES.get(start_key)
    destination_coords = CITY_COORDINATES.get(destination_key)
    cache_pair = pair_key(start_key, destination_key) if start_key and destination_key else ("", "")
    cache_key = (cache_pair[0], cache_pair[1], bool(use_online))
    now = time.time()

    def build_distance_result(distance_km: float | None, distance_display: str, source: str) -> dict[str, object]:
        return {
            "route_name": f"{start_label} to {destination_label}",
            "distance_km": distance_km,
            "distance_display": distance_display,
            "source": source,
            "start_name": start_label,
            "destination_name": destination_label,
            "start_coords": (
                {"lat": round(start_coords[0], 6), "lng": round(start_coords[1], 6)} if start_coords else None
            ),
            "destination_coords": (
                {"lat": round(destination_coords[0], 6), "lng": round(destination_coords[1], 6)}
                if destination_coords
                else None
            ),
        }

    def finalize(distance_km: float | None, distance_display: str, source: str) -> dict[str, object]:
        result = build_distance_result(distance_km, distance_display, source)
        if cache_key[0] and cache_key[1]:
            DISTANCE_RESULT_CACHE[cache_key] = (
                now,
                {
                    "distance_km": result["distance_km"],
                    "distance_display": result["distance_display"],
                    "source": result["source"],
                },
            )
        return result

    if not start_key or not destination_key:
        return build_distance_result(None, "Distance unavailable", "invalid")

    cached_entry = DISTANCE_RESULT_CACHE.get(cache_key)
    if cached_entry and now - cached_entry[0] <= DISTANCE_CACHE_TTL_SEC:
        cached_payload = cached_entry[1]
        return build_distance_result(
            cached_payload.get("distance_km"),
            str(cached_payload.get("distance_display", "Distance unavailable")),
            str(cached_payload.get("source", "cache")),
        )

    if start_key == destination_key:
        return finalize(0.0, "0.0 km", "same-place")

    lookup = ROAD_DISTANCE_KM.get(pair_key(start_key, destination_key))
    if lookup is not None:
        return finalize(lookup, f"{lookup:.1f} km", "road-table")

    if not start_coords or not destination_coords:
        return finalize(None, "Distance unavailable for this location pair", "unknown")

    if use_online:
        osrm_distance = fetch_osrm_distance_km(start_coords, destination_coords)
        if osrm_distance is not None:
            return finalize(osrm_distance, f"{osrm_distance:.1f} km", "osrm")

    aerial = haversine_km(start_coords[0], start_coords[1], destination_coords[0], destination_coords[1])
    estimated_road = round(aerial * 1.2, 1)
    return finalize(estimated_road, f"{estimated_road:.1f} km (estimated)", "estimated")


def safe_eval_expression(expression: str) -> float | None:
    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = _eval(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPERATORS:
            left = _eval(node.left)
            right = _eval(node.right)
            return SAFE_OPERATORS[type(node.op)](left, right)
        raise ValueError("Unsupported expression")

    try:
        tree = ast.parse(expression, mode="eval")
        return _eval(tree)
    except (SyntaxError, ValueError, ZeroDivisionError):
        return None


def maybe_answer_math(question: str) -> str | None:
    lowered = question.lower().strip()
    if not any(token in lowered for token in ["calculate", "solve", "what is", "=", "+", "-", "*", "/", "%"]):
        return None

    candidate = re.sub(r"[^0-9\.\+\-\*\/%\(\)\s]", " ", question)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if len(candidate) < 3:
        return None

    result = safe_eval_expression(candidate)
    if result is None:
        return None

    if result.is_integer():
        return f"The answer is {int(result)}."
    return f"The answer is {round(result, 6)}."


def answer_from_local_knowledge(question: str) -> str | None:
    lowered = question.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s]", "", lowered)

    capital_match = re.search(r"capital of ([a-z\s]+)", normalized)
    if capital_match:
        country = re.sub(r"\s+", " ", capital_match.group(1)).strip()
        capital = COUNTRY_CAPITALS.get(country)
        if capital:
            return f"The capital of {country.title()} is {capital}."

    distance_match = re.search(r"distance from ([a-z\s]+) to ([a-z\s]+)", normalized)
    if distance_match:
        start = re.sub(r"\s+", " ", distance_match.group(1)).strip()
        destination = re.sub(r"\s+", " ", distance_match.group(2)).strip()
        route = compute_trip_distance(start, destination)
        return f"Distance from {route['route_name']} is {route['distance_display']}."

    if "who are you" in normalized:
        return "I am your TravelAxis assistant. I can answer travel and general questions."

    if "today date" in normalized or "current date" in normalized:
        from datetime import datetime

        return f"Today's date is {datetime.now().strftime('%B %d, %Y')}."

    if "help" in normalized and "what can you do" in normalized:
        return (
            "I can create itineraries, estimate travel distance, split expenses, "
            "suggest hotels/activities, and answer general questions."
        )

    for topic, explanation in GENERAL_TOPIC_EXPLAINERS.items():
        if topic in normalized:
            return explanation

    return None


TRAVEL_AGENT_LLM_PROMPT = (
    "You are TravelAxis AI, an India-focused travel assistant for group trips. "
    "Give realistic, trustworthy answers grounded in provided context. "
    "Rules: "
    "Use provided Trip context and Grounded travel facts as source-of-truth for exact names, prices, and distances. "
    "Do not invent live facts (seat availability, exact live fares, contact numbers, weather, or surge prices). "
    "If live data is missing, say it clearly and provide practical estimate ranges. "
    "Keep answers concise, structured, and actionable. Use sections when useful: Overview, Plan, Estimated Cost, Travel Tips. "
    "For train planning, request missing details: departure city, destination city, travel date, travelers, budget, and preference (fastest/cheapest/comfortable). "
    "Always state assumptions in one short line."
)


def _build_grounded_facts_for_llm(travel_context: dict[str, object]) -> list[str]:
    facts: list[str] = []

    starting_point = str(travel_context.get("starting_point", "")).strip()
    destination = str(travel_context.get("destination", "")).strip()
    visited_place = str(travel_context.get("visited_place", "")).strip()
    active_place = destination or visited_place
    budget = max(10000, _to_int(travel_context.get("budget"), 20000))

    if active_place:
        profile = get_destination_profile(active_place)
        best_months = str(profile.get("best_months", "")).strip()
        if best_months:
            facts.append(f"Best season reference: {best_months}")

        famous_spots, _ = get_destination_famous_spots(active_place, profile, limit=5)
        if famous_spots:
            facts.append("Top spots: " + "; ".join(famous_spots[:5]))

        foods_raw = profile.get("foods", [])
        foods = foods_raw if isinstance(foods_raw, list) else []
        food_items = [str(item).strip() for item in foods if isinstance(item, str) and str(item).strip()]
        if food_items:
            facts.append("Food references: " + "; ".join(food_items[:3]))

        hotels_raw = profile.get("hotels", [])
        hotels = hotels_raw if isinstance(hotels_raw, list) else []
        hotel_lines: list[str] = []
        for hotel in hotels[:3]:
            if not isinstance(hotel, dict):
                continue
            hotel_name = str(hotel.get("name", "")).strip()
            if not hotel_name:
                continue
            hotel_price = _to_int(hotel.get("price"), 0)
            hotel_area = str(hotel.get("area", "city center")).strip() or "city center"
            if hotel_price > 0:
                hotel_lines.append(f"{hotel_name} (Rs {hotel_price}/night, Near {hotel_area})")
            else:
                hotel_lines.append(f"{hotel_name} (Near {hotel_area})")

        if not hotel_lines:
            generated_hotels = build_spot_based_hotels(active_place, budget, profile, limit=3)
            for hotel in generated_hotels[:3]:
                hotel_name = str(hotel.get("name", "")).strip()
                if not hotel_name:
                    continue
                hotel_price = _to_int(hotel.get("price"), 0)
                hotel_area = str(hotel.get("area", "city center")).strip() or "city center"
                if hotel_price > 0:
                    hotel_lines.append(f"{hotel_name} (Rs {hotel_price}/night, Near {hotel_area})")
                else:
                    hotel_lines.append(f"{hotel_name} (Near {hotel_area})")

        if hotel_lines:
            facts.append("Hotel references: " + "; ".join(hotel_lines[:3]))

    if starting_point and active_place:
        route_info = compute_trip_distance(starting_point, active_place, use_online=False)
        distance_display = str(route_info.get("distance_display", "")).strip()
        source = str(route_info.get("source", "")).strip()
        if distance_display:
            source_text = f" ({source})" if source else ""
            facts.append(f"Road distance reference: {distance_display}{source_text}")

    return facts


def _build_travel_context_suffix(travel_context: dict[str, object] | None) -> str:
    if not isinstance(travel_context, dict):
        return ""

    starting_point = str(travel_context.get("starting_point", "")).strip()
    destination = str(travel_context.get("destination", "")).strip()
    visited_place = str(travel_context.get("visited_place", "")).strip()
    people = _to_int(travel_context.get("people"), 0)
    budget = _to_int(travel_context.get("budget"), 0)

    context_lines: list[str] = [f"Date context: {datetime.now().strftime('%Y-%m-%d')}"]
    if starting_point:
        context_lines.append(f"Starting point: {starting_point}")
    if destination:
        context_lines.append(f"Destination: {destination}")
    if visited_place:
        context_lines.append(f"Visited place context: {visited_place}")
    if people > 0:
        context_lines.append(f"Travelers: {people}")
    if budget > 0:
        context_lines.append(f"Budget: Rs {budget}")

    sections = ["Trip context:\n" + "\n".join(f"- {line}" for line in context_lines)]

    grounded_facts = _build_grounded_facts_for_llm(travel_context)
    if grounded_facts:
        sections.append("Grounded travel facts:\n" + "\n".join(f"- {fact}" for fact in grounded_facts))

    return "\n\n" + "\n\n".join(section for section in sections if section.strip())

def fetch_deepseek_answer(question: str, travel_context: dict[str, object] | None = None) -> str | None:
    api_key = DEEPSEEK_API_KEY
    if not api_key:
        return None

    model = DEEPSEEK_MODEL or "deepseek-chat"
    question_text = question.strip()
    if not question_text:
        return None

    context_suffix = _build_travel_context_suffix(travel_context)
    user_prompt = (
        f"User question:\n{question_text}\n"
        f"{context_suffix}\n\n"
        "Respond realistically using grounded context. Mark any changing values as approximate."
    ).strip()
    endpoint = "https://api.deepseek.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": TRAVEL_AGENT_LLM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 480,
        "top_p": 0.9,
    }

    req = urlrequest.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=9) as response:
            data = json.loads(response.read().decode("utf-8"))

        choices = data.get("choices", [])
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message", {})
                if not isinstance(message, dict):
                    continue
                content = str(message.get("content", "")).strip()
                if content:
                    return content
        return None
    except (urlerror.URLError, TimeoutError, ValueError, KeyError, TypeError):
        return None


def answer_general_question(
    question: str, travel_context: dict[str, object] | None = None
) -> str | None:
    math_answer = maybe_answer_math(question)
    if math_answer:
        return math_answer

    local_answer = answer_from_local_knowledge(question)
    if local_answer:
        return local_answer

    deepseek_answer = fetch_deepseek_answer(question, travel_context=travel_context)
    if deepseek_answer:
        return deepseek_answer

    return None

def _extract_route_cities_from_text(message: str) -> tuple[str | None, str | None]:
    lowered = normalize_place(message)
    patterns = [
        r"\bfrom\s+([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s+(?:on|for|with|under|by|in|date|tomorrow|today)\b|$)",
        r"\b([a-z\s]+?)\s+to\s+([a-z\s]+?)(?:\s+(?:on|for|with|under|by|in|date|tomorrow|today)\b|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if not match:
            continue
        departure_candidate = match.group(1).strip()
        destination_candidate = match.group(2).strip()
        departure_key = detect_known_place_key(departure_candidate)
        destination_key = detect_known_place_key(destination_candidate)
        if departure_key and destination_key and departure_key != destination_key:
            return display_place_name(departure_key), display_place_name(destination_key)
    return None, None


def _extract_train_date(message: str) -> str | None:
    lowered = message.lower()
    if "today" in lowered:
        return datetime.now().strftime("%Y-%m-%d")
    if "tomorrow" in lowered:
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    numeric_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", message)
    if numeric_match:
        return numeric_match.group(1)

    month_match = re.search(
        r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(?:\d{4})?)\b",
        lowered,
    )
    if month_match:
        return month_match.group(1).title()
    return None


def _extract_train_travelers(message: str) -> int | None:
    match = re.search(r"\b(\d{1,2})\s*(?:people|persons|travellers|travelers|members|adults)\b", message.lower())
    if not match:
        return None
    return max(1, _to_int(match.group(1), 1))


def _detect_train_preference(message: str) -> str | None:
    lower = message.lower()
    if any(word in lower for word in ["fastest", "quick", "earliest", "minimum time"]):
        return "fastest"
    if any(word in lower for word in ["cheapest", "lowest", "budget", "low cost", "affordable"]):
        return "cheapest"
    if any(word in lower for word in ["comfortable", "comfort", "ac", "luxury", "premium"]):
        return "comfortable"
    return None


def _collect_train_request_details(message: str, context: dict[str, object], memory: dict[str, object]) -> dict[str, object]:
    train_memory_raw = memory.get("train_context", {}) if isinstance(memory, dict) else {}
    train_memory = train_memory_raw if isinstance(train_memory_raw, dict) else {}

    departure_city, destination_city = _extract_route_cities_from_text(message)

    if not departure_city:
        departure_city = str(train_memory.get("departure_city", "")).strip() or str(context.get("starting_point", "")).strip()
    if not destination_city:
        destination_city = str(train_memory.get("destination_city", "")).strip() or str(context.get("destination", "")).strip()

    travel_date = _extract_train_date(message) or str(train_memory.get("travel_date", "")).strip()

    travelers = _extract_train_travelers(message)
    if travelers is None:
        travelers = max(0, _to_int(train_memory.get("travelers"), 0))
    if travelers <= 0:
        travelers = max(0, _to_int(context.get("people"), 0))

    budget = _extract_budget(message)
    if budget is None:
        budget = max(0, _to_int(train_memory.get("budget"), 0))
    if budget <= 0:
        budget = max(0, _to_int(context.get("budget"), 0))

    preference = _detect_train_preference(message) or str(train_memory.get("preference", "")).strip().lower()

    return {
        "departure_city": departure_city,
        "destination_city": destination_city,
        "travel_date": travel_date,
        "travelers": travelers,
        "budget": budget,
        "preference": preference,
    }


def _missing_train_fields(details: dict[str, object]) -> list[str]:
    missing: list[str] = []
    if not str(details.get("departure_city", "")).strip():
        missing.append("Departure city")
    if not str(details.get("destination_city", "")).strip():
        missing.append("Destination city")
    if not str(details.get("travel_date", "")).strip():
        missing.append("Travel date")
    if _to_int(details.get("travelers"), 0) <= 0:
        missing.append("Number of travelers")
    if _to_int(details.get("budget"), 0) <= 0:
        missing.append("Budget")
    if str(details.get("preference", "")).strip().lower() not in {"fastest", "cheapest", "comfortable"}:
        missing.append("Travel preference (fastest / cheapest / comfortable)")
    return missing


def _duration_to_minutes(duration_text: str) -> int:
    hour_match = re.search(r"(\d+)\s*h", duration_text.lower())
    minute_match = re.search(r"(\d+)\s*m", duration_text.lower())
    hours = _to_int(hour_match.group(1), 0) if hour_match else 0
    minutes = _to_int(minute_match.group(1), 0) if minute_match else 0
    return max(1, hours * 60 + minutes)


def _add_minutes_to_time(time_text: str, minutes: int) -> str:
    try:
        base = datetime.strptime(time_text, "%H:%M")
        target = base + timedelta(minutes=minutes)
        return target.strftime("%H:%M")
    except ValueError:
        return time_text


def _build_fallback_train_options(
    departure_city: str, destination_city: str, budget: int, route_info: dict[str, object]
) -> list[dict[str, object]]:
    distance = _parse_numeric_value(route_info.get("distance_km"))
    if distance is None:
        distance = 650.0

    base_minutes = max(300, int((distance / 55) * 60))
    base_price = max(350, int(distance * 1.05))

    fastest_minutes = max(220, int(base_minutes * 0.82))
    regular_minutes = max(260, int(base_minutes * 0.95))
    sleeper_minutes = max(320, int(base_minutes * 1.08))

    def duration_label(total_minutes: int) -> str:
        return f"{total_minutes // 60}h {total_minutes % 60}m"

    comfort_multiplier = 1.15 if budget >= 35000 else 1.0

    return [
        {
            "name": f"{departure_city} {destination_city} Superfast",
            "number": "12901",
            "departure": "06:10",
            "arrival": _add_minutes_to_time("06:10", fastest_minutes),
            "duration": duration_label(fastest_minutes),
            "classes": {
                "CC": int(base_price * 1.15 * comfort_multiplier),
                "3A": int(base_price * 1.45 * comfort_multiplier),
                "2A": int(base_price * 2.05 * comfort_multiplier),
            },
        },
        {
            "name": f"{departure_city} {destination_city} Express",
            "number": "12681",
            "departure": "14:35",
            "arrival": _add_minutes_to_time("14:35", regular_minutes),
            "duration": duration_label(regular_minutes),
            "classes": {
                "SL": int(base_price * 0.72),
                "3A": int(base_price * 1.35),
                "2A": int(base_price * 1.95),
            },
        },
        {
            "name": f"{departure_city} {destination_city} Night Mail",
            "number": "17039",
            "departure": "21:20",
            "arrival": _add_minutes_to_time("21:20", sleeper_minutes),
            "duration": duration_label(sleeper_minutes),
            "classes": {
                "2S": int(base_price * 0.45),
                "SL": int(base_price * 0.68),
                "3A": int(base_price * 1.28),
            },
        },
    ]


def _get_train_options_for_route(
    departure_city: str,
    destination_city: str,
    preference: str,
    budget: int,
    route_info: dict[str, object],
) -> list[dict[str, object]]:
    departure_key = normalize_place(departure_city)
    destination_key = normalize_place(destination_city)

    options = TRAIN_ROUTE_LIBRARY.get((departure_key, destination_key))
    if not options:
        reverse_options = TRAIN_ROUTE_LIBRARY.get((destination_key, departure_key))
        if reverse_options:
            options = reverse_options

    if not options:
        options = _build_fallback_train_options(departure_city, destination_city, budget, route_info)

    normalized_options = [deepcopy(option) for option in options]

    if preference == "fastest":
        normalized_options.sort(key=lambda option: _duration_to_minutes(str(option.get("duration", "0h 0m"))))
    elif preference == "cheapest":
        normalized_options.sort(
            key=lambda option: min(
                int(price) for price in (option.get("classes", {}) or {"SL": 999999}).values() if isinstance(price, (int, float))
            )
        )
    elif preference == "comfortable":
        def comfort_score(option: dict[str, object]) -> int:
            classes = option.get("classes", {})
            if not isinstance(classes, dict):
                return 0
            score = 0
            if "1A" in classes:
                score += 4
            if "2A" in classes:
                score += 3
            if "3A" in classes:
                score += 2
            if "EC" in classes:
                score += 2
            if "CC" in classes:
                score += 1
            return score

        normalized_options.sort(key=comfort_score, reverse=True)

    return normalized_options[:3]


def _choose_recommended_class(option: dict[str, object], preference: str) -> tuple[str, int]:
    classes_raw = option.get("classes", {})
    classes = classes_raw if isinstance(classes_raw, dict) else {}
    if not classes:
        return "SL", 0

    if preference == "cheapest":
        code = min(classes, key=lambda cls: _to_int(classes.get(cls), 999999))
        return code, _to_int(classes.get(code), 0)

    if preference == "comfortable":
        for code in ["1A", "2A", "EC", "3A", "CC", "SL", "2S"]:
            if code in classes:
                return code, _to_int(classes.get(code), 0)

    for code in ["3A", "CC", "SL", "2A", "2S", "EC", "1A"]:
        if code in classes:
            return code, _to_int(classes.get(code), 0)

    fallback_code = next(iter(classes.keys()))
    return fallback_code, _to_int(classes.get(fallback_code), 0)


def _format_train_classes(classes: dict[str, int]) -> str:
    items: list[str] = []
    for code, price in sorted(classes.items(), key=lambda item: _to_int(item[1], 0)):
        label = TRAIN_CLASS_LABELS.get(code, code)
        items.append(f"{label} (Rs {_to_int(price, 0)})")
    return ", ".join(items)


def _build_train_itinerary_lines(
    days: int,
    departure_city: str,
    destination_city: str,
    travel_date: str,
    attractions: list[str],
    foods: list[str],
) -> list[str]:
    safe_attractions = _ensure_min_items(attractions, max(4, days + 1), destination_city)
    safe_foods = _ensure_min_items(foods, 3, destination_city)

    lines = [
        f"Day 1: Board train from {departure_city} on {travel_date}, arrive at {destination_city}, check-in, and evening visit to {safe_attractions[0]}",
        f"Day 2: Explore {safe_attractions[1]} and {safe_attractions[2]}, then try {safe_foods[0]}",
    ]
    for day in range(3, days + 1):
        spot = safe_attractions[(day - 1) % len(safe_attractions)]
        food = safe_foods[(day - 1) % len(safe_foods)]
        lines.append(f"Day {day}: Local sightseeing at {spot}, food stop: {food}, and flexible evening plan")
    return lines


def _build_train_planner_reply(
    details: dict[str, object],
    train_options: list[dict[str, object]],
    route_info: dict[str, object],
    attractions: list[str],
    foods: list[str],
    hotels: list[dict[str, object]],
    requested_days: int,
) -> str:
    departure_city = str(details.get("departure_city", "")).strip()
    destination_city = str(details.get("destination_city", "")).strip()
    travel_date = str(details.get("travel_date", "")).strip()
    travelers = max(1, _to_int(details.get("travelers"), 1))
    budget = max(1, _to_int(details.get("budget"), 1))
    preference = str(details.get("preference", "fastest")).strip().lower() or "fastest"

    train_lines: list[str] = []
    for index, option in enumerate(train_options, 1):
        classes_raw = option.get("classes", {})
        classes = classes_raw if isinstance(classes_raw, dict) else {}
        classes_display = _format_train_classes(classes) if classes else "Class details unavailable"
        train_lines.append(
            f"{index}. {option.get('name', 'Train Option')} ({option.get('number', 'N/A')})\n"
            f"   Departure: {option.get('departure', 'N/A')} | Arrival: {option.get('arrival', 'N/A')} | Duration: {option.get('duration', 'N/A')}\n"
            f"   Classes: {classes_display}"
        )

    primary_option = train_options[0] if train_options else {"classes": {"SL": 0}}
    class_code, ticket_per_person = _choose_recommended_class(primary_option, preference)
    selected_class_label = TRAIN_CLASS_LABELS.get(class_code, class_code)

    total_ticket_cost = ticket_per_person * travelers
    avg_hotel_price = 0
    if hotels:
        avg_hotel_price = sum(_to_int(hotel.get("price"), 0) for hotel in hotels[:3]) // max(1, min(3, len(hotels)))
    stay_nights = max(1, requested_days - 1)
    total_stay_cost = avg_hotel_price * stay_nights
    local_buffer = max(1500, travelers * 400)
    grand_total = total_ticket_cost + total_stay_cost + local_buffer
    split_per_person = grand_total // travelers

    suggested_itinerary = _build_train_itinerary_lines(
        requested_days,
        departure_city,
        destination_city,
        travel_date,
        attractions,
        foods,
    )

    hotel_lines: list[str] = []
    for hotel in hotels[:3]:
        hotel_lines.append(
            f"- {hotel.get('name', 'Hotel')} | Rs {_to_int(hotel.get('price'), 0)}/night | Near {hotel.get('area', 'station area')}"
        )
    hotels_section = "\n".join(hotel_lines) if hotel_lines else "- Hotel suggestions will appear after route confirmation"

    travel_tips = [
        "Book 3-6 weeks early for better group seat allocation.",
        "For groups, prefer one PNR per coach and keep a nearby coach fallback.",
        "Try lower berths for seniors and mid-berths for flexible swaps.",
        "Set departure reminder: T-24h, T-6h, and T-2h.",
    ]

    return (
        f"Train Options ({departure_city} -> {destination_city})\n"
        + "\n".join(train_lines)
        + "\n\nEstimated Cost\n"
        + f"- Preference: {preference.title()}\n"
        + f"- Recommended class: {selected_class_label} (Approx Rs {ticket_per_person}/person)\n"
        + f"- Ticket total for {travelers} travelers: Rs {total_ticket_cost}\n"
        + f"- Stay estimate ({stay_nights} night(s)): Rs {total_stay_cost}\n"
        + f"- Local transfer/food buffer: Rs {local_buffer}\n"
        + f"- Estimated group total: Rs {grand_total}\n"
        + f"- Expense split per person: Rs {split_per_person}\n"
        + f"- Budget reference: Rs {budget}\n"
        + f"- Route distance reference: {route_info.get('distance_display', 'N/A')}\n"
        + "\nSuggested Itinerary\n"
        + "\n".join(suggested_itinerary)
        + "\n\nNearby Stays & Food\n"
        + hotels_section
        + f"\n- Food picks: {foods[0]}, {foods[1]}\n"
        + "\nTravel Tips\n"
        + "\n".join([f"- {tip}" for tip in travel_tips])
        + "\n\nNote: Real-time train data is not integrated yet. These are realistic sample options and prices may vary."
    )

def _normalize_profile_text_list(raw: object, fallback: list[str]) -> list[str]:
    items: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                value = item.strip()
                if value:
                    items.append(value)
    if items:
        return items
    return [value for value in fallback if isinstance(value, str) and value.strip()]


def _normalize_profile_activities(raw: object, place_title: str) -> list[dict[str, int | str]]:
    activities: list[dict[str, int | str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                activities.append(
                    {
                        "name": name,
                        "price": max(300, _to_int(item.get("price"), 1200)),
                    }
                )
    if activities:
        return activities
    return [
        {"name": f"Guided city walk in {place_title}", "price": 900},
        {"name": f"Local cultural experience in {place_title}", "price": 1300},
        {"name": f"Sunset viewpoint transfer in {place_title}", "price": 800},
        {"name": f"Adventure activity in {place_title}", "price": 1800},
    ]


def _ensure_min_items(items: list[str], minimum: int, fallback_prefix: str) -> list[str]:
    cleaned = [item.strip() for item in items if isinstance(item, str) and item.strip()]
    if not cleaned:
        cleaned = [f"{fallback_prefix} highlight"]
    while len(cleaned) < minimum:
        cleaned.append(cleaned[len(cleaned) % len(cleaned)])
    return cleaned


def _extract_requested_days(message: str, default_days: int) -> int:
    match = re.search(r"\b([2-9]|1[0-4])\s*(?:day|days)\b", message.lower())
    if not match:
        return default_days
    return max(2, min(10, _to_int(match.group(1), default_days)))


def _build_itinerary_for_days(
    destination: str, budget: int, requested_days: int, attraction_pool: list[str]
) -> list[dict[str, str]]:
    base = build_itinerary(destination, budget)
    if requested_days <= len(base):
        return base[:requested_days]

    extended = list(base)
    while len(extended) < requested_days:
        day_num = len(extended) + 1
        spot = attraction_pool[(day_num - 1) % len(attraction_pool)]
        extended.append(
            {
                "day": day_num,
                "title": f"Keep this day flexible: explore {spot}, enjoy nearby cafes, and reserve time for photos and local markets.",
            }
        )
    return extended


def _pick_primary_intent(intents: set[str]) -> str:
    priority = [
        "itinerary",
        "hotel",
        "food",
        "activity",
        "places",
        "nearby",
        "route",
        "budget",
        "history",
        "shopping",
        "transport",
        "summary",
        "safety",
        "packing",
    ]
    for intent in priority:
        if intent in intents:
            return intent
    return "general"


def _next_destination_prompt(primary_intent: str, place_title: str) -> str:
    prompts = {
        "itinerary": f"Ask: optimize this itinerary for your budget in {place_title}",
        "hotel": f"Ask: compare top 3 hotels in {place_title} with pros and cons",
        "food": f"Ask: best breakfast, lunch, and dinner options in {place_title}",
        "activity": f"Ask: activities in {place_title} with time slots and total cost",
        "places": f"Ask: add entry fee and best visiting time for top spots in {place_title}",
        "nearby": f"Ask: nearby day-trip places from {place_title} with travel time",
        "route": "Ask: best departure time and road stops for this route",
        "budget": "Ask: split this trip into stay, transport, food, and activities",
        "transport": f"Ask: best local transport pass/options in {place_title}",
        "shopping": f"Ask: where to buy authentic local items in {place_title}",
        "history": f"Ask: 5 quick facts and best season to visit {place_title}",
        "summary": "Ask: convert this into a day-wise checklist",
        "general": f"Ask: full recommendation for {place_title} (spots + food + hotel + budget)",
    }
    return prompts.get(primary_intent, prompts["general"])


def generate_chat_reply(
    message: str, context: dict[str, object], memory: dict[str, object] | None = None
) -> tuple[str, dict[str, object]]:
    text = (message or "").strip()
    lower = text.lower()
    memory = memory if isinstance(memory, dict) else {}

    starting_point = str(context.get("starting_point", "")).strip()
    destination_context = str(context.get("destination", "")).strip()
    active_place, visited_mode = resolve_active_place(text, context, destination_context)

    mentioned_place = detect_known_place_key(text)
    memory_place = str(memory.get("last_place", "")).strip()
    destination_changed = (
        bool(destination_context and memory_place)
        and normalize_place(destination_context) != normalize_place(memory_place)
    )

    # If user changed destination in context, force chatbot focus to the new destination.
    if destination_changed:
        active_place = destination_context
        visited_mode = False

    if (
        not mentioned_place
        and memory_place
        and not destination_changed
        and any(token in lower for token in ["there", "that place", "this place", "same place", "it"])
    ):
        active_place = memory_place
        if "visited" in lower:
            visited_mode = True

    active_place_key = resolve_place_key(active_place)
    active_place_title = KNOWN_PLACE_DISPLAY.get(normalize_place(active_place)) or (
        display_place_name(active_place_key) if active_place_key else "your destination"
    )
    people = max(1, _to_int(context.get("people"), 4))
    budget = max(10000, _to_int(context.get("budget"), 20000))
    total_expense = max(5000, _to_int(context.get("total_expense"), int(budget * 0.9)))
    llm_context = {
        "starting_point": starting_point,
        "destination": destination_context or active_place,
        "visited_place": active_place if visited_mode else "",
        "people": people,
        "budget": budget,
        "total_expense": total_expense,
    }

    assistant_mode = str(memory.get("assistant_mode", "")).strip().lower()
    train_followup_markers = {"yes", "yeah", "yup", "ok", "okay", "more", "next", "continue", "details"}
    train_followup_terms = [
        "update",
        "change",
        "modify",
        "budget",
        "date",
        "people",
        "traveler",
        "travelers",
        "preference",
        "class",
        "hotel",
        "itinerary",
        "food",
        "attraction",
        "tip",
        "route",
    ]
    train_keyword_pattern = (
        r"\b(train|rail|railway|pnr|tatkal|berth|coach|sleeper|shatabdi|rajdhani|vande bharat|"
        r"station|platform|3a|2a|1a|sl|cc|ec|2s)\b"
    )
    has_route_phrase = bool(re.search(r"\bfrom\b.+\bto\b", lower))
    has_train_keyword = bool(re.search(train_keyword_pattern, lower))
    has_train_trip_context = has_route_phrase and any(
        token in lower
        for token in ["people", "person", "traveller", "traveler", "members", "budget", "date", "day", "days"]
    )
    continuing_train_flow = assistant_mode == "train" and (
        lower in train_followup_markers
        or any(term in lower for term in train_followup_terms)
        or has_route_phrase
    )
    train_mode_requested = has_train_keyword or has_train_trip_context or continuing_train_flow

    if train_mode_requested:
        train_details = _collect_train_request_details(text, context, memory)
        train_departure = str(train_details.get("departure_city", "")).strip()
        train_destination = str(train_details.get("destination_city", "")).strip()

        if train_departure and train_destination and normalize_place(train_departure) == normalize_place(train_destination):
            same_city_reply = (
                "Departure and destination are the same. Please share a different destination city for train planning."
            )
            new_state = {
                "assistant_mode": "train",
                "train_context": train_details,
                "last_place": train_destination or active_place,
                "visited_mode": False,
                "last_intent": "train_validation",
                "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
            }
            return same_city_reply, new_state

        missing_train_fields = _missing_train_fields(train_details)
        if missing_train_fields:
            known_lines: list[str] = []
            if train_departure:
                known_lines.append(f"Departure city: {train_departure}")
            if train_destination:
                known_lines.append(f"Destination city: {train_destination}")
            if str(train_details.get("travel_date", "")).strip():
                known_lines.append(f"Travel date: {train_details['travel_date']}")
            if _to_int(train_details.get("travelers"), 0) > 0:
                known_lines.append(f"Travelers: {_to_int(train_details['travelers'], 0)}")
            if _to_int(train_details.get("budget"), 0) > 0:
                known_lines.append(f"Budget: Rs {_to_int(train_details['budget'], 0)}")
            if str(train_details.get("preference", "")).strip():
                known_lines.append(f"Preference: {str(train_details['preference']).title()}")

            known_section = ""
            if known_lines:
                known_section = "\n\nCaptured so far:\n" + "\n".join(f"- {line}" for line in known_lines)

            missing_section = "\n".join(f"- {field}" for field in missing_train_fields)
            ask_reply = (
                "I can plan your group train trip. I still need:\n"
                f"{missing_section}"
                f"{known_section}\n\n"
                "Share in one line: from city, to city, date, travelers, budget, and preference (fastest/cheapest/comfortable)."
            )
            new_state = {
                "assistant_mode": "train",
                "train_context": train_details,
                "last_place": train_destination or active_place,
                "visited_mode": False,
                "last_intent": "train_requirements",
                "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
            }
            return ask_reply, new_state

        train_budget = max(10000, _to_int(train_details.get("budget"), budget))
        train_preference = str(train_details.get("preference", "fastest")).strip().lower() or "fastest"
        train_details["budget"] = train_budget
        train_details["preference"] = train_preference

        train_route_info = compute_trip_distance(train_departure, train_destination)
        train_profile = get_destination_profile(train_destination)
        train_famous_spots, _ = get_destination_famous_spots(train_destination, train_profile, limit=8)
        train_attraction_candidates = _normalize_profile_text_list(train_profile.get("attractions"), train_famous_spots)
        train_attractions = _ensure_min_items(
            _unique_keep_order(train_attraction_candidates + train_famous_spots),
            6,
            train_destination.title(),
        )
        train_foods = _ensure_min_items(
            _normalize_profile_text_list(train_profile.get("foods"), [f"Local cuisine trail in {train_destination.title()}"]),
            3,
            train_destination.title(),
        )
        train_hotels = get_destination_hotels(train_destination, train_budget, limit=4)
        requested_days = _extract_requested_days(text, 3 if train_budget <= 30000 else 4)
        train_options = _get_train_options_for_route(
            train_departure,
            train_destination,
            train_preference,
            train_budget,
            train_route_info,
        )
        train_reply = _build_train_planner_reply(
            train_details,
            train_options,
            train_route_info,
            train_attractions,
            train_foods,
            train_hotels,
            requested_days,
        )
        train_state = {
            "assistant_mode": "train",
            "train_context": {
                "departure_city": train_departure,
                "destination_city": train_destination,
                "travel_date": str(train_details.get("travel_date", "")).strip(),
                "travelers": _to_int(train_details.get("travelers"), people),
                "budget": train_budget,
                "preference": train_preference,
            },
            "last_place": train_destination,
            "visited_mode": False,
            "last_intent": "train_plan",
            "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
        }
        return train_reply, train_state

    destination_required_terms = [
        "itinerary",
        "destination",
        "famous",
        "nearby",
        "hotel",
        "food",
        "activity",
        "route",
        "distance",
        "budget",
        "transport",
        "shopping",
        "weather",
        "best time",
    ]
    has_explicit_destination_context = bool(destination_context or mentioned_place or memory_place or active_place.strip())
    asks_destination_guidance = any(term in lower for term in destination_required_terms)
    if not has_explicit_destination_context and asks_destination_guidance:
        ask_destination_reply = (
            "To give accurate destination-based answers, please share at least the destination place.\n"
            "For route support, share in one line: from <starting point> to <destination>."
        )
        new_state = {
            "last_place": active_place,
            "visited_mode": visited_mode,
            "last_intent": "destination_required",
            "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
        }
        return ask_destination_reply, new_state

    profile = get_destination_profile(active_place)
    famous_spots, _ = get_destination_famous_spots(active_place, profile, limit=8)
    attraction_candidates = _normalize_profile_text_list(profile.get("attractions"), famous_spots)
    attractions = _ensure_min_items(_unique_keep_order(attraction_candidates + famous_spots), 6, active_place_title)

    nearby_candidates = _normalize_profile_text_list(profile.get("nearby_spots"), attractions)
    nearby_spots = _ensure_min_items(_unique_keep_order(nearby_candidates + attractions), 4, active_place_title)

    foods = _ensure_min_items(
        _normalize_profile_text_list(profile.get("foods"), [f"Local cuisine trail in {active_place_title}"]),
        3,
        active_place_title,
    )
    shopping = _ensure_min_items(
        _normalize_profile_text_list(profile.get("shopping"), [f"Main market in {active_place_title}"]),
        3,
        active_place_title,
    )
    transport = _ensure_min_items(
        _normalize_profile_text_list(profile.get("transport"), [f"City cab circuit in {active_place_title}"]),
        3,
        active_place_title,
    )
    activities = _normalize_profile_activities(profile.get("activities"), active_place_title)

    destination_hotels = get_destination_hotels(active_place, budget, limit=4)
    parsed_route_start, parsed_route_end = _extract_route_cities_from_text(text)
    route_start = parsed_route_start or starting_point
    route_destination = parsed_route_end or active_place
    route_info = compute_trip_distance(route_start, route_destination)

    is_greeting = bool(re.search(r"\b(hi|hello|hey|namaste)\b", lower)) or "good morning" in lower or "good evening" in lower
    is_help_query = any(phrase in lower for phrase in ["what can you do", "help", "commands"])

    intent_keywords = {
        "itinerary": ["itinerary", "day wise", "day-wise", "schedule", "plan"],
        "places": ["places", "attractions", "sightseeing", "must visit", "famous spot", "famous spots"],
        "nearby": ["nearby", "near me", "close by"],
        "food": ["food", "eat", "cuisine", "restaurant"],
        "activity": ["activity", "activities", "adventure", "nightlife", "things to do"],
        "hotel": ["hotel", "stay", "resort", "accommodation"],
        "budget": ["budget", "expense", "split", "cost", "pay", "cheap", "save", "optimize"],
        "route": ["route", "distance", "how far", "travel", "how to reach"],
        "history": ["history", "historical", "culture", "heritage", "tradition", "best time", "best month", "season", "weather"],
        "shopping": ["shopping", "shop", "souvenir", "buy", "market items"],
        "transport": ["transport", "taxi", "cab", "bus", "metro", "scooter", "commute"],
        "safety": ["safety", "safe", "secure", "emergency"],
        "packing": ["packing", "pack", "carry", "essentials"],
        "summary": ["summary", "final plan", "overall plan"],
    }

    intents: set[str] = set()
    for intent, keywords in intent_keywords.items():
        if any(keyword in lower for keyword in keywords):
            intents.add(intent)

    is_full_recommendation = any(
        phrase in lower
        for phrase in [
            "full plan",
            "complete plan",
            "full destination plan",
            "overall recommendation",
            "recommend all",
        ]
    )
    is_generic_recommendation = any(phrase in lower for phrase in ["recommend", "suggest", "what should i do"])

    if is_full_recommendation or (is_generic_recommendation and not intents):
        intents.update({"places", "nearby", "food", "activity", "hotel", "budget"})

    followup_markers = {"yes", "yeah", "yup", "ok", "okay", "more", "next", "continue", "details"}
    if lower in followup_markers:
        last_intent = str(memory.get("last_intent", "")).strip()
        if last_intent:
            intents.add(last_intent)

    travel_signal_words = [
        "trip",
        "travel",
        "destination",
        "itinerary",
        "hotel",
        "budget",
        "distance",
        "route",
        "famous",
        "food",
        "activity",
        "visited place",
        "shopping",
    ]
    has_travel_signal = any(signal in lower for signal in travel_signal_words)
    has_known_place_signal = bool(mentioned_place)
    has_destination_context = bool(destination_context)

    # Keep chatbot in travel-assistant mode whenever a destination context exists.
    if (has_travel_signal or has_known_place_signal or has_destination_context) and not intents and not is_help_query and not is_greeting:
        intents.update({"places", "food", "activity"})

    if not (has_travel_signal or has_known_place_signal or has_destination_context):
        general_answer = answer_general_question(text, travel_context=llm_context)
        if general_answer:
            new_state = {
                "last_place": active_place,
                "visited_mode": visited_mode,
                "last_intent": "general",
                "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
            }
            return general_answer, new_state

    if is_greeting and not intents and not is_help_query:
        mode_text = "visited-place guidance" if visited_mode else "destination guidance"
        reply = (
            f"Hi! I am ready for {mode_text} in {active_place_title}.\n"
            "Ask directly: itinerary, famous spots, nearby spots, food, activities, hotels, budget split, or route."
        )
        new_state = {
            "last_place": active_place,
            "visited_mode": visited_mode,
            "last_intent": "help",
            "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
        }
        return reply, new_state

    if is_help_query:
        help_reply = (
            "You can ask in one line, for example:\n"
            "1. '3 day itinerary for Manali with famous spots'\n"
            "2. 'Nearby spots + food + activities in Jaipur'\n"
            "3. 'Best hotels in Goa under 5000 with prices'\n"
            "4. 'Distance and route from Delhi to Mahabaleshwar'\n"
            "5. 'Split budget 30000 for 5 people'"
        )
        new_state = {
            "last_place": active_place,
            "visited_mode": visited_mode,
            "last_intent": "help",
            "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
        }
        return help_reply, new_state

    sections: list[str] = []

    if "itinerary" in intents:
        default_days = 4 if budget <= 30000 else 5
        requested_days = _extract_requested_days(text, default_days)
        itinerary = _build_itinerary_for_days(active_place, budget, requested_days, attractions)
        itinerary_lines = [f"Day {item['day']}: {item['title']}" for item in itinerary]
        sections.append(
            f"Itinerary for {active_place_title} ({requested_days} days):\n"
            + "\n".join(itinerary_lines)
        )

    if "places" in intents:
        sections.append(
            f"Must-visit famous spots in {active_place_title}:\n"
            f"1. {attractions[0]}\n"
            f"2. {attractions[1]}\n"
            f"3. {attractions[2]}\n"
            f"4. {attractions[3]}"
        )

    if "nearby" in intents and "hotel" not in intents:
        label = "Nearby famous spots around your visited place" if visited_mode else "Nearby famous spots around"
        sections.append(
            f"{label} {active_place_title}:\n"
            f"1. {nearby_spots[0]}\n"
            f"2. {nearby_spots[1]}\n"
            f"3. {nearby_spots[2]}\n"
            f"4. {nearby_spots[3]}"
        )

    if "food" in intents:
        prefix = "Food recommendations for your visited place" if visited_mode else "Food recommendations for"
        sections.append(
            f"{prefix} {active_place_title}:\n"
            f"1. {foods[0]}\n"
            f"2. {foods[1]}\n"
            f"3. {foods[2]}"
        )

    if "activity" in intents:
        activity_lines = [
            f"{index + 1}. {item['name']} (Approx Rs {item['price']})" for index, item in enumerate(activities[:4])
        ]
        prefix = "Top activities in your visited place" if visited_mode else "Top activities in"
        sections.append(f"{prefix} {active_place_title}:\n" + "\n".join(activity_lines))

    if "hotel" in intents:
        if destination_hotels:
            hotel_lines = []
            for hotel in destination_hotels[:4]:
                hotel_lines.append(
                    f"- {hotel['name']} | Rs {hotel['price']}/night | Near {hotel.get('area', 'city center')} | {hotel['rating']}/5"
                )
            prefix = "Recommended nearby hotels for your visited place" if visited_mode else "Recommended nearby hotels in"
            sections.append(f"{prefix} {active_place_title}:\n" + "\n".join(hotel_lines))
        else:
            sections.append(f"I could not fetch hotels right now for {active_place_title}. Please try again in a moment.")

    if "history" in intents:
        sections.append(
            f"History and culture of {active_place_title}:\n"
            f"History: {profile['history_note']}\n"
            f"Culture: {profile['culture_note']}\n"
            f"Best season: {profile['best_months']}"
        )

    if "shopping" in intents:
        sections.append(
            f"Shopping picks in {active_place_title}:\n"
            f"1. {shopping[0]}\n"
            f"2. {shopping[1]}\n"
            f"3. {shopping[2]}"
        )

    if "transport" in intents:
        sections.append(
            f"Local transport options in {active_place_title}:\n"
            f"1. {transport[0]}\n"
            f"2. {transport[1]}\n"
            f"3. {transport[2]}"
        )

    if "budget" in intents:
        requested_budget = _extract_budget(lower)
        active_budget = max(10000, requested_budget) if requested_budget else budget
        estimated_total = int(active_budget * 0.9)
        per_person = estimated_total // people
        sections.append(
            f"Budget split for {active_place_title}:\n"
            f"Estimated total: Rs {estimated_total}\n"
            f"People: {people}\n"
            f"Per person: Rs {per_person}\n"
            "Model: 45% stay + 25% transport + 20% activities + 10% food buffer"
        )

    if "route" in intents:
        if not route_start or not route_destination:
            sections.append(
                "Share route in this format for exact distance: from <starting point> to <destination>."
            )
        elif route_info["distance_km"] is None:
            sections.append(
                f"Route: {route_info['route_name']}\n"
                "Distance not available for this pair yet. Try major city names for best accuracy."
            )
        else:
            sections.append(
                f"Road route: {route_info['route_name']}\n"
                f"Distance: {route_info['distance_display']}\n"
                "Tip: keep one fixed local cab block each day for better group coordination."
            )


    if "safety" in intents:
        sections.append(
            "Group safety checklist:\n"
            "1. Share live location in a group.\n"
            "2. Keep one emergency budget reserve.\n"
            "3. Avoid isolated routes after late evening.\n"
            "4. Save local emergency and hotel contacts offline."
        )

    if "packing" in intents:
        sections.append(
            "Smart packing checklist:\n"
            "1. IDs, bookings, emergency contacts\n"
            "2. Weather-ready clothing and comfortable shoes\n"
            "3. Medicines, sunscreen, basic first aid\n"
            "4. Chargers, power bank, one shared utility pouch"
        )

    if "summary" in intents:
        sections.append(
            f"Trip summary ({starting_point.title()} to {active_place_title}):\n"
            f"- Travelers: {people}\n"
            f"- Budget: Rs {budget}\n"
            f"- Estimated spend: Rs {total_expense}\n"
            f"- Per person: Rs {total_expense // people}\n"
            f"- Route: {route_info['distance_display']}"
        )

    if not sections:
        general_answer = answer_general_question(text, travel_context=llm_context)
        if general_answer:
            sections.append(general_answer)
        else:
            sections.append(
                f"I can help with {active_place_title}. Tell me exactly what you need: itinerary, hotels, famous spots, food, activities, budget split, or route distance."
            )

    primary_intent = _pick_primary_intent(intents)
    sections.append("Next best prompt:\n" + _next_destination_prompt(primary_intent, active_place_title))
    state_last_place = route_destination if ("route" in intents and route_destination) else active_place
    new_state = {
        "last_place": state_last_place,
        "visited_mode": visited_mode,
        "last_intent": primary_intent,
        "turn_count": max(0, _to_int(memory.get("turn_count"), 0)) + 1,
    }

    return "\n\n".join(section.strip() for section in sections if section.strip()), new_state


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    if session.get("user"):
        return redirect(url_for("dashboard"))

    form = {"login_id": ""}
    errors: dict[str, str] = {}

    if request.method == "POST":
        form, errors = validate_login_form(
            {
                "login_id": request.form.get("login_id", ""),
                "password": request.form.get("password", ""),
            }
        )
        if not errors:
            login_key = normalize_login_identifier(form["login_id"])
            existing = USER_STORE.get(login_key)
            if existing:
                if existing["password"] != form["password"]:
                    errors["password"] = "Incorrect password."
            else:
                USER_STORE[login_key] = {
                    "login_id": form["login_id"],
                    "display_name": display_name_from_login_id(form["login_id"]),
                    "password": form["password"],
                }
                flash("New account created and logged in.", "success")

            if not errors:
                user = USER_STORE[login_key]
                session["user"] = {
                    "login_id": user["login_id"],
                    "display_name": user["display_name"],
                }
                return redirect(url_for("dashboard"))

    return render_template("login.html", form=form, errors=errors)


@app.post("/forgot-password")
def forgot_password():
    recovery_identifier = request.form.get("recovery_identifier", "").strip()
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    identifier_error = validate_login_identifier(recovery_identifier)
    if identifier_error:
        flash(identifier_error, "error")
        return redirect(url_for("login"))

    password_error = validate_password_strength(new_password)
    if password_error:
        flash(password_error, "error")
        return redirect(url_for("login"))

    if new_password != confirm_password:
        flash("Confirm password does not match new password.", "error")
        return redirect(url_for("login"))

    login_key = normalize_login_identifier(recovery_identifier)
    if login_key not in USER_STORE:
        flash("Account not found. Login once to create account, then reset password.", "error")
        return redirect(url_for("login"))

    USER_STORE[login_key]["password"] = new_password
    flash("Password reset successful. Please login with the new password.", "success")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET", "POST"])
def dashboard() -> str:
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    saved_form = session.get("trip_form", {})
    form = {
        "starting_point": str(saved_form.get("starting_point", "")).strip(),
        "destination": str(saved_form.get("destination", "")).strip(),
        "people": max(1, _to_int(saved_form.get("people"), 4)),
        "budget": max(10000, _to_int(saved_form.get("budget"), 20000)),
    }
    action_output = (
        f"Welcome {user['display_name']}. Use dashboard controls to plan trip, split expenses, and open Hotels/AI Chatbot pages."
    )

    if request.method == "POST":
        form["starting_point"] = request.form.get("starting_point", "").strip()
        form["destination"] = request.form.get("destination", "").strip()
        form["people"] = max(1, _to_int(request.form.get("people"), 4))
        form["budget"] = max(10000, _to_int(request.form.get("budget"), 20000))
        action_output = (
            f"Itinerary generated for {form['destination'].title()} with {form['people']} people and "
            f"budget Rs {form['budget']}."
        )
    else:
        # Preserve state when returning from details pages via query params.
        if request.args:
            form["starting_point"] = request.args.get("starting_point", form["starting_point"]).strip() or form["starting_point"]
            form["destination"] = request.args.get("destination", form["destination"]).strip() or form["destination"]
            form["people"] = max(1, _to_int(request.args.get("people"), form["people"]))
            form["budget"] = max(10000, _to_int(request.args.get("budget"), form["budget"]))

    session["trip_form"] = form

    itinerary = build_itinerary(form["destination"], form["budget"])
    destination_profile = get_destination_profile(form["destination"])
    famous_spots, famous_spots_source = get_destination_famous_spots(
        form["destination"], destination_profile, limit=6
    )
    all_hotels = get_destination_hotels(form["destination"], form["budget"], limit=8)
    hotels = all_hotels[:2]
    hotel_markers = build_hotel_map_markers([hotel for hotel in all_hotels if isinstance(hotel, dict)])
    total_expense = int(form["budget"] * 0.9)
    per_person = total_expense // form["people"]
    route_info = compute_trip_distance(form["starting_point"], form["destination"])

    return render_template(
        "index.html",
        form=form,
        itinerary=itinerary,
        famous_spots=famous_spots,
        famous_spots_source=famous_spots_source,
        hotels=hotels,
        total_expense=total_expense,
        per_person=per_person,
        action_output=action_output,
        user=user,
        route_info=route_info,
        hotel_markers=hotel_markers,
        india_places=INDIA_WANDER_PLACES,
        google_maps_api_key=GOOGLE_MAPS_API_KEY,
        quick_replies=DEFAULT_QUICK_REPLIES,
    )



@app.route("/hotels")
def hotels_page() -> str:
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    saved_form = session.get("trip_form", {})
    form = {
        "starting_point": str(saved_form.get("starting_point", "")).strip(),
        "destination": str(saved_form.get("destination", "")).strip(),
        "people": max(1, _to_int(saved_form.get("people"), 4)),
        "budget": max(10000, _to_int(saved_form.get("budget"), 20000)),
    }
    if request.args:
        form["starting_point"] = request.args.get("starting_point", form["starting_point"]).strip() or form["starting_point"]
        form["destination"] = request.args.get("destination", form["destination"]).strip() or form["destination"]
        form["people"] = max(1, _to_int(request.args.get("people"), form["people"]))
        form["budget"] = max(10000, _to_int(request.args.get("budget"), form["budget"]))

    session["trip_form"] = form

    show_hotels = bool(form["starting_point"].strip() and form["destination"].strip())
    hotels = get_destination_hotels(form["destination"], form["budget"], limit=10) if show_hotels else []
    route_info = (
        compute_trip_distance(form["starting_point"], form["destination"])
        if show_hotels
        else {
            "route_name": "Route pending",
            "distance_display": "Enter starting point and destination",
            "source": "input-required",
            "distance_km": None,
            "start_name": "Start",
            "destination_name": "Destination",
        }
    )
    return render_template(
        "hotels_page.html",
        user=user,
        form=form,
        hotels=hotels,
        route_info=route_info,
        show_hotels=show_hotels,
    )


@app.route("/chatbot")
def chatbot_page() -> str:
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    saved_form = session.get("trip_form", {})
    form = {
        "starting_point": str(saved_form.get("starting_point", "")).strip(),
        "destination": str(saved_form.get("destination", "")).strip(),
        "people": max(1, _to_int(saved_form.get("people"), 4)),
        "budget": max(10000, _to_int(saved_form.get("budget"), 20000)),
    }
    if request.args:
        form["starting_point"] = request.args.get("starting_point", form["starting_point"]).strip() or form["starting_point"]
        form["destination"] = request.args.get("destination", form["destination"]).strip() or form["destination"]
        form["people"] = max(1, _to_int(request.args.get("people"), form["people"]))
        form["budget"] = max(10000, _to_int(request.args.get("budget"), form["budget"]))

    session["trip_form"] = form

    total_expense = int(form["budget"] * 0.9)
    return render_template(
        "chatbot_page.html",
        user=user,
        form=form,
        total_expense=total_expense,
        india_places=INDIA_WANDER_PLACES,
        quick_replies=DEFAULT_QUICK_REPLIES,
        action_output="AI Travel Assistant is ready. Ask any destination or visited-place question.",
    )


@app.route("/hotels/detail")
def hotel_details_page() -> str:
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    destination = request.args.get("destination", "").strip()
    budget = max(10000, _to_int(request.args.get("budget"), 30000))
    people = max(1, _to_int(request.args.get("people"), 4))
    selected_hotel_slug = slugify(request.args.get("hotel", ""))
    starting_point = request.args.get("starting_point", "").strip()

    hotels = get_destination_hotels(destination, budget, limit=None)
    selected_hotel = find_hotel_by_slug(hotels, selected_hotel_slug)
    if not selected_hotel and hotels:
        selected_hotel = hotels[0]
    if not selected_hotel:
        return redirect(url_for("dashboard"))

    # Show random contact details each time a hotel is opened from "Select Hotel".
    selected_hotel = deepcopy(selected_hotel)
    random_contact = default_hotel_contact(
        str(selected_hotel.get("name", "Hotel Stay")),
        destination,
        str(selected_hotel.get("area", "City Center")),
    )
    selected_hotel["contact_phone"] = random_contact["phone"]
    selected_hotel["contact_email"] = random_contact["email"]
    selected_hotel["address"] = random_contact["address"]

    selected_price = _to_int(selected_hotel.get("price"), 0)
    compare_hotels = []
    for hotel in hotels:
        if hotel.get("slug") == selected_hotel.get("slug"):
            continue
        price = _to_int(hotel.get("price"), 0)
        compare_hotels.append(
            {
                "name": hotel.get("name", ""),
                "price": price,
                "rating": hotel.get("rating", 0),
                "area": hotel.get("area", ""),
                "price_diff": price - selected_price,
                "slug": hotel.get("slug", ""),
                "booking_url": hotel.get("booking_url", ""),
            }
        )
    compare_hotels = sorted(compare_hotels, key=lambda item: item["price"])

    route_info = compute_trip_distance(starting_point, destination)

    return render_template(
        "hotel_details.html",
        user=user,
        destination=destination,
        starting_point=starting_point,
        budget=budget,
        people=people,
        hotel=selected_hotel,
        compare_hotels=compare_hotels,
        route_info=route_info,
    )


@app.route("/api/chat", methods=["POST"])
def chat_api():
    if not session.get("user"):
        return jsonify({"reply": "Session expired. Please login again."}), 401

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    context = payload.get("context", {})

    if not message:
        return jsonify({"reply": "Please enter a message so I can help with your trip."}), 400
    if not isinstance(context, dict):
        context = {}

    chat_state = session.get("chat_state", {})
    if not isinstance(chat_state, dict):
        chat_state = {}

    trip_form = session.get("trip_form", {})
    if not isinstance(trip_form, dict):
        trip_form = {}

    context_starting = str(context.get("starting_point", "")).strip()
    context_destination = str(context.get("destination", "")).strip()

    if not context_starting:
        context_starting = str(trip_form.get("starting_point", "")).strip()
        if context_starting:
            context["starting_point"] = context_starting

    if not context_destination:
        context_destination = str(trip_form.get("destination", "")).strip()
        if context_destination:
            context["destination"] = context_destination

    # Persist latest chat context so destination changes immediately reflect across pages.
    if context_starting or context_destination:
        updated_trip_form = dict(trip_form)
        if context_starting:
            updated_trip_form["starting_point"] = context_starting
        if context_destination:
            updated_trip_form["destination"] = context_destination

        people_value = _to_int(context.get("people"), 0)
        budget_value = _to_int(context.get("budget"), 0)
        if people_value > 0:
            updated_trip_form["people"] = people_value
        if budget_value > 0:
            updated_trip_form["budget"] = budget_value
        session["trip_form"] = updated_trip_form

    if context_destination:
        previous_place = str(chat_state.get("last_place", "")).strip()
        if not previous_place or normalize_place(previous_place) != normalize_place(context_destination):
            chat_state["last_place"] = context_destination
            chat_state["visited_mode"] = False
            chat_state.pop("assistant_mode", None)
            chat_state.pop("last_intent", None)

    reply, updated_state = generate_chat_reply(message, context, chat_state)
    session["chat_state"] = updated_state
    return jsonify({"reply": reply})


@app.route("/api/distance", methods=["POST"])
def distance_api():
    if not session.get("user"):
        return jsonify({"message": "Session expired. Please login again."}), 401

    payload = request.get_json(silent=True) or {}
    starting_point = str(payload.get("starting_point", "")).strip()
    destination = str(payload.get("destination", "")).strip()

    if not starting_point or not destination:
        return jsonify({"message": "Please provide both starting point and destination."}), 400

    route_info = compute_trip_distance(starting_point, destination)
    if route_info["distance_km"] is None:
        return jsonify(route_info), 404
    return jsonify(route_info)


if __name__ == "__main__":
    app.run(debug=True)
