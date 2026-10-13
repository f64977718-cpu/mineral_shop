from django.core.management.base import BaseCommand
from django.utils.text import slugify
from store.models import Category, Mineral

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e", "є": "ie",
    "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i", "к": "k", "л": "l",
    "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ь": "",
    "ю": "iu", "я": "ia", "'": "", "\u2019": "",
}


def translit_slug(text):
    text = text.lower()
    out = "".join(TRANSLIT.get(ch, ch) for ch in text)
    return slugify(out)


CATEGORIES = [
    {"name": "Аметист", "slug": "amethyst", "description": "Фіолетова відміна кварцу — від ніжного лаванду до глибокого сибірського фіолету."},
    {"name": "Кварц", "slug": "quartz", "description": "Прозорий гірський кришталь та його друзи — класика будь-якої колекції."},
    {"name": "Цитрин", "slug": "citrine", "description": "Сонячний жовто-медовий кварц, який рідко зустрічається в природному вигляді."},
    {"name": "Рожевий кварц", "slug": "rose-quartz", "description": "М'який рожевий кварц, галтований або у вигляді необробленого шматка."},
    {"name": "Турмалін", "slug": "tourmaline", "description": "Чорний та поліхромний турмалін у вигляді призматичних кристалів."},
    {"name": "Агат", "slug": "agate", "description": "Смугастий халцедон із мальовничими природними візерунками."},
    {"name": "Малахіт", "slug": "malachite", "description": "Смарагдово-зелений мінерал із характерним концентричним малюнком."},
    {"name": "Лабрадорит", "slug": "labradorite", "description": "Мінерал із переливчастим ефектом лабрадоресценції — синім і зеленим сяйвом."},
]

MINERALS = [
    dict(cat="amethyst", name="Аметистова друза \"Ніч над Ріо-Гранде\"", price=2400, old_price=2900, weight=850,
         origin="brazil", c1="#8D6BD4", c2="#3B2E5E", shape="cluster",
         short="Велика друза глибокого фіолетового кольору на природній основі.",
         desc="Природна друза аметисту з родовища Ріо-Гранде-ду-Сул. Кристали мають насичений фіолетовий колір, що переходить у майже чорний в глибині граней. Чудово виглядає як самостійний інтер'єрний об'єкт."),
    dict(cat="amethyst", name="Аметистовий жезл вістрям", price=680, old_price=None, weight=120,
         origin="uruguay", c1="#9B7FDB", c2="#4A3A73", shape="point",
         short="Класичний одинарний кристал аметисту з чіткою гранню.",
         desc="Прозорий, добре сформований кристал аметисту з Уругваю. Підходить для медитативних практик та як настільний акцент."),
    dict(cat="amethyst", name="Аметист \"Шеврон\" полірований", price=540, old_price=None, weight=210,
         origin="madagascar", c1="#7C5CBF", c2="#2E2447", shape="tumbled",
         short="Смугастий аметист-кварц із контрастними шевронними лініями.",
         desc="Галтований зразок аметисту-шеврона з характерними білими смугами кварцу. Приємний на дотик, добре лежить у долоні."),
    dict(cat="quartz", name="Гірський кришталь, друза-щітка", price=1200, old_price=None, weight=640,
         origin="brazil", c1="#E7E3F5", c2="#8C86A8", shape="cluster",
         short="Прозора друза кришталю з десятками гострих вершин.",
         desc="Класична щітка гірського кришталю. Кристали прозорі, з природними включеннями, що заломлюють світло."),
    dict(cat="quartz", name="Кришталевий кристал-генератор", price=950, weight=310,
         origin="brazil", c1="#F2F0FA", c2="#9089AE", shape="point",
         short="Одинарний вирівняний кристал кварцу правильної шестигранної форми.",
         desc="Великий одинарний кристал гірського кришталю з майже ідеальною шестигранною огранкою природного походження."),
    dict(cat="citrine", name="Цитринова щітка \"Мед Мінас-Жерайс\"", price=1650, old_price=1950, weight=480,
         origin="brazil", c1="#E7C878", c2="#8C6A24", shape="cluster",
         short="Насичена медово-жовта друза натурального цитрину.",
         desc="Рідкісний природний (не термооброблений) цитрин із теплим медовим відтінком. Родовище — Мінас-Жерайс, Бразилія."),
    dict(cat="citrine", name="Цитриновий кристал-вістря", price=420, old_price=None, weight=95,
         origin="brazil", c1="#EBCF86", c2="#A47C2B", shape="point",
         short="Компактний прозорий кристал теплого жовтого кольору.",
         desc="Невеликий, але дуже чистий кристал цитрину з насиченим бурштиновим відтінком."),
    dict(cat="rose-quartz", name="Рожевий кварц, галтований середній", price=280, old_price=None, weight=140,
         origin="madagascar", c1="#EAB6C0", c2="#B06E7D", shape="tumbled",
         short="М'яко-рожевий галтований камінь із легким блиском.",
         desc="Гладко відполірований рожевий кварц пастельного відтінку — популярний вибір для дому та подарунків."),
    dict(cat="rose-quartz", name="Необроблений шматок рожевого кварцу", price=520, old_price=650, weight=390,
         origin="madagascar", c1="#D98C97", c2="#8A4E58", shape="tumbled",
         short="Природна необроблена брила рожевого кварцу насиченого тону.",
         desc="Великий цільний шматок рожевого кварцу без огранки — зберігає природну фактуру мінералу."),
    dict(cat="tourmaline", name="Чорний турмалін, призма", price=780, old_price=None, weight=160,
         origin="brazil", c1="#4B4750", c2="#111014", shape="point",
         short="Видовжений призматичний кристал чорного турмаліну (шерл).",
         desc="Чорний турмалін (шерл) із чіткою призматичною структурою та природною штриховкою на гранях."),
    dict(cat="agate", name="Агатовий зріз \"Синя лагуна\"", price=890, old_price=None, weight=220,
         origin="uruguay", c1="#6FA3C7", c2="#2C4E63", shape="tumbled",
         short="Поліграний зріз агату з концентричними синьо-сірими смугами.",
         desc="Декоративний зріз уругвайського агату з чіткими концентричними шарами блакитного та сірого відтінків."),
    dict(cat="malachite", name="Малахіт, поліграний шматок", price=1100, old_price=1300, weight=310,
         origin="congo", c1="#4FA377", c2="#1F5238", shape="tumbled",
         short="Насичено-зелений малахіт з характерним смугастим малюнком.",
         desc="Конголезький малахіт із класичним концентричним візерунком у відтінках смарагдового та темно-зеленого."),
    dict(cat="labradorite", name="Лабрадорит з ефектом лабрадоресценції", price=760, old_price=None, weight=280,
         origin="madagascar", c1="#3E5B73", c2="#16232E", shape="tumbled",
         short="Сірий камінь із синьо-зеленими спалахами під кутом світла.",
         desc="Мадагаскарський лабрадорит із вираженим ефектом лабрадоресценції — синьо-зелене сяйво з'являється при повороті каменя на світлі."),
]


class Command(BaseCommand):
    help = "Наповнює магазин демонстраційними категоріями та мінералами."

    def handle(self, *args, **options):
        cat_objs = {}
        for c in CATEGORIES:
            obj, _ = Category.objects.update_or_create(
                slug=c["slug"], defaults={"name": c["name"], "description": c["description"]}
            )
            cat_objs[c["slug"]] = obj

        created = 0
        for i, m in enumerate(MINERALS):
            slug = translit_slug(m["name"])[:60] or f"mineral-{i}"

            Mineral.objects.update_or_create(
                slug=slug,
                defaults=dict(
                    category=cat_objs[m["cat"]],
                    name=m["name"],
                    short_description=m["short"],
                    description=m["desc"],
                    price=m["price"],
                    old_price=m.get("old_price"),
                    weight_grams=m["weight"],
                    origin=m["origin"],
                    color_primary=m["c1"],
                    color_secondary=m["c2"],
                    shape=m["shape"],
                    stock=12 if i % 5 else 0,
                    is_featured=i < 6,
                ),
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Готово: {len(cat_objs)} категорій, {created} мінералів."))
