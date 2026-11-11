"""Currículo do canal: espécies reais, matérias e valores com versículos (Almeida)."""

# (nome em português, nome em inglês para a imagem, chave que precisa aparecer na narração)
ESPECIES = [
    ("capivara", "capybara", "capivar"),
    ("tamanduá-bandeira", "giant anteater", "tamandua"),
    ("arara-azul", "hyacinth macaw parrot", "arara"),
    ("tucano", "toco toucan bird", "tucan"),
    ("jabuti", "red-footed tortoise", "jabuti"),
    ("boto-cor-de-rosa", "pink Amazon river dolphin", "boto"),
    ("mico-leão-dourado", "golden lion tamarin monkey", "mico"),
    ("quati", "coati", "quati"),
    ("tatu", "armadillo", "tatu"),
    ("lobo-guará", "maned wolf", "lobo"),
    ("peixe-boi", "manatee", "peixe-boi"),
    ("onça-pintada", "jaguar cub", "onc"),
    ("bicho-preguiça", "three-toed sloth", "pregui"),
    ("sapinho", "small green tree frog", "sap"),
    ("tartaruga-marinha", "sea turtle", "tartaruga"),
    ("cachorrinho", "puppy dog", "cachorr"),
    ("gatinho", "kitten", "gat"),
    ("coelhinho", "bunny rabbit", "coelh"),
    ("ovelhinha", "lamb", "ovelh"),
    ("pintinho", "baby chick", "pint"),
    ("patinho", "duckling", "pat"),
    ("bezerrinho", "calf", "bezerr"),
    ("elefantinho", "baby elephant", "elefant"),
    ("girafinha", "baby giraffe", "giraf"),
    ("leãozinho", "lion cub", "leao"),
    ("pinguim", "penguin chick", "pinguim"),
    ("corujinha", "baby owl", "coruj"),
    ("esquilo", "squirrel", "esquil"),
    ("ursinho-panda", "panda cub", "panda"),
    ("raposinha", "red fox kit", "rapos"),
]

MATERIAS = {
    "matemática": [
        "contar de 1 a 10", "somar pequenas quantidades até 10", "formas geométricas: círculo, quadrado e triângulo",
        "maior e menor", "dividir em partes iguais: a metade", "sequências e padrões de cores", "os dias da semana",
    ],
    "português": [
        "as vogais A, E, I, O, U", "palavras que rimam", "dividir palavras em sílabas",
        "palavras que começam com a mesma letra", "as palavras mágicas: por favor, obrigado, com licença e desculpe",
        "opostos: grande e pequeno, alto e baixo",
    ],
    "geografia": [
        "a Floresta Amazônica", "o Pantanal", "o Cerrado", "a Caatinga", "a Mata Atlântica", "os Pampas",
        "os pontos cardeais: norte, sul, leste e oeste", "o planeta Terra, os rios e os oceanos",
    ],
    "ciências": [
        "o ciclo da água e a chuva", "as plantas precisam de sol, água e terra", "o dia e a noite",
        "as quatro estações do ano", "como a lagarta vira borboleta", "os cinco sentidos", "o que cada animal come",
    ],
    "educação moral e cívica": [
        "respeitar a fila e esperar a vez", "cuidar dos lugares públicos e não jogar lixo no chão",
        "a bandeira do Brasil e suas cores", "a faixa de pedestre e o semáforo", "ajudar e respeitar os mais velhos",
        "cumprir combinados e promessas",
    ],
    "saúde e higiene": [
        "lavar as mãos", "escovar os dentes", "comer frutas e verduras", "beber água", "dormir cedo e bem", "tomar banho",
    ],
    "segurança": [
        "não mexer em tomadas", "não brincar com fogo nem fósforos", "usar cinto de segurança no carro",
        "não sair com estranhos e ficar perto dos pais", "cuidado com objetos cortantes",
        "atravessar a rua de mãos dadas com um adulto",
    ],
}

# valor: [(referência escrita, referência falada, texto)]
VALORES = {
    "amizade": [("Provérbios 17:17", "Provérbios, capítulo 17, versículo 17", "Em todo o tempo ama o amigo.")],
    "generosidade": [
        ("Atos 20:35", "Atos, capítulo 20, versículo 35", "Mais bem-aventurada coisa é dar do que receber."),
        ("2 Coríntios 9:7", "Segunda carta aos Coríntios, capítulo 9, versículo 7", "Deus ama ao que dá com alegria."),
    ],
    "honestidade": [("Efésios 4:25", "Efésios, capítulo 4, versículo 25",
                     "Deixai a mentira e falai a verdade cada um com o seu próximo.")],
    "obediência aos pais": [
        ("Efésios 6:1", "Efésios, capítulo 6, versículo 1", "Filhos, sede obedientes a vossos pais no Senhor, porque isto é justo."),
        ("Êxodo 20:12", "Êxodo, capítulo 20, versículo 12", "Honra a teu pai e a tua mãe."),
    ],
    "gratidão": [("1 Tessalonicenses 5:18", "Primeira carta aos Tessalonicenses, capítulo 5, versículo 18", "Em tudo dai graças.")],
    "perdão": [("Efésios 4:32", "Efésios, capítulo 4, versículo 32",
                "Sede uns para com os outros benignos, misericordiosos, perdoando-vos uns aos outros.")],
    "coragem": [
        ("Josué 1:9", "Josué, capítulo 1, versículo 9",
         "Esforça-te e tem bom ânimo; não temas, porque o Senhor, teu Deus, é contigo por onde quer que andares."),
        ("Salmos 56:3", "Salmo 56, versículo 3", "Em qualquer tempo em que eu temer, confiarei em ti."),
    ],
    "perseverança": [("Gálatas 6:9", "Gálatas, capítulo 6, versículo 9", "E não nos cansemos de fazer o bem.")],
    "paciência": [("Eclesiastes 3:1", "Eclesiastes, capítulo 3, versículo 1", "Tudo tem o seu tempo determinado.")],
    "amor ao próximo": [
        ("Mateus 22:39", "Mateus, capítulo 22, versículo 39", "Amarás o teu próximo como a ti mesmo."),
        ("Gálatas 6:2", "Gálatas, capítulo 6, versículo 2", "Levai as cargas uns dos outros."),
    ],
    "respeito": [
        ("Mateus 7:12", "Mateus, capítulo 7, versículo 12",
         "Tudo o que vós quereis que os homens vos façam, fazei-lho também vós."),
        ("1 Samuel 16:7", "Primeiro livro de Samuel, capítulo 16, versículo 7",
         "O homem vê o que está diante dos olhos, porém o Senhor olha para o coração."),
    ],
    "gentileza": [("Provérbios 15:1", "Provérbios, capítulo 15, versículo 1", "A resposta branda desvia o furor.")],
    "responsabilidade": [
        ("Colossenses 3:23", "Colossenses, capítulo 3, versículo 23",
         "Tudo quanto fizerdes, fazei-o de todo o coração, como ao Senhor."),
        ("Provérbios 6:6", "Provérbios, capítulo 6, versículo 6",
         "Vai ter com a formiga, ó preguiçoso; olha para os seus caminhos e sê sábio."),
    ],
    "sabedoria": [("Provérbios 1:5", "Provérbios, capítulo 1, versículo 5", "O sábio ouvirá e crescerá em ciência.")],
    "cuidado com a criação": [
        ("Gênesis 1:31", "Gênesis, capítulo 1, versículo 31", "E viu Deus tudo quanto tinha feito, e eis que era muito bom."),
        ("Salmos 24:1", "Salmo 24, versículo 1", "Do Senhor é a terra e a sua plenitude."),
    ],
    "paz": [("Mateus 5:9", "Mateus, capítulo 5, versículo 9",
             "Bem-aventurados os pacificadores, porque eles serão chamados filhos de Deus.")],
    "alegria": [("Salmos 118:24", "Salmo 118, versículo 24",
                 "Este é o dia que fez o Senhor; regozijemo-nos e alegremo-nos nele.")],
    "humildade": [("Filipenses 2:3", "Filipenses, capítulo 2, versículo 3", "Cada um considere os outros superiores a si mesmo.")],
}


# Anatomia em inglês de cada protagonista: vai no início do prompt de imagem.
APARENCIA = {
    "capivara": "a large barrel-shaped rodent with a blunt square snout, small rounded ears, reddish-brown fur and no tail",
    "tamanduá-bandeira": "a giant anteater with a very long thin tubular snout, tiny mouth, small round ears, a huge bushy fan-like tail, gray-brown fur and a bold black-and-white diagonal stripe across the shoulder",
    "arara-azul": "a hyacinth macaw parrot with cobalt-blue feathers, a yellow ring around the eyes, a yellow patch at the base of a large curved black beak and a long tail",
    "tucano": "a toco toucan bird with black feathers, a white throat and a huge bright orange beak with a black tip",
    "jabuti": "a red-footed tortoise with a high domed dark shell with yellow patches and red-orange scales on the legs and head",
    "boto-cor-de-rosa": "a pink Amazon river dolphin with a long thin beak-like snout, rounded forehead and smooth pink skin, living in a river",
    "mico-leão-dourado": "a golden lion tamarin monkey with long shiny golden-orange fur forming a lion-like mane around a small dark face, and a long tail",
    "quati": "a coati with a long pointed upturned snout, brown fur and a long ringed striped tail held upright",
    "tatu": "an armadillo with a banded armored shell, pointed snout, small ears, short legs and a scaly tail",
    "lobo-guará": "a maned wolf with very long thin black legs, reddish-orange fur, big upright ears, a black mane on the neck and a white-tipped tail",
    "peixe-boi": "a manatee, a large round gray aquatic mammal with paddle-shaped flippers, a flat rounded tail and a whiskered snout, living in water",
    "onça-pintada": "a jaguar cub, a golden-yellow big cat cub covered with black rosette spots",
    "bicho-preguiça": "a three-toed sloth with shaggy gray-brown fur, a round face with dark eye stripes and a gentle smile, long arms with three long curved claws, hanging from branches",
    "sapinho": "a small bright green tree frog with big round eyes and round sticky toe pads",
    "tartaruga-marinha": "a sea turtle with a smooth streamlined shell and large paddle flippers, swimming in the ocean",
    "cachorrinho": "a puppy dog with floppy ears and a wagging tail",
    "gatinho": "a kitten with pointed ears, whiskers and a long tail",
    "coelhinho": "a bunny rabbit with long upright ears, a fluffy round tail and a twitching nose",
    "ovelhinha": "a lamb with fluffy white curly wool and a small face and legs",
    "pintinho": "a baby chick, a tiny fluffy yellow bird with a small orange beak",
    "patinho": "a duckling, a fluffy yellow baby duck with a flat orange bill and webbed feet",
    "bezerrinho": "a calf, a young cow with small horn buds, big ears and hooves",
    "elefantinho": "a baby elephant with gray skin, a long trunk and big floppy ears",
    "girafinha": "a baby giraffe with a very long neck, a tan-and-brown spotted pattern and two small horns on the head",
    "leãozinho": "a lion cub, a golden-tan big cat cub with round ears and a tufted tail",
    "pinguim": "a penguin chick, fluffy gray and white, with a small black beak and flippers",
    "corujinha": "a baby owl, fluffy and round, with huge round eyes, a small hooked beak and ear tufts",
    "esquilo": "a squirrel, a small rodent with a big bushy curled tail and small rounded ears",
    "ursinho-panda": "a panda cub, a black-and-white bear cub with black eye patches, black ears and black legs",
    "raposinha": "a red fox kit with orange-red fur, a white chest, pointed ears and a bushy white-tipped tail",
}


# Protagonistas que a IA de imagem gratuita não desenha bem (testado: saem com patas, híbridos ou espécie errada).
# Ficam fora do sorteio; voltam se um motor de imagem melhor entrar no canal.
DIFICEIS_IMAGEM = {"peixe-boi", "boto-cor-de-rosa", "tartaruga-marinha", "tamanduá-bandeira", "tatu", "jabuti"}

# Coadjuvantes que a IA desenha bem (lista entregue ao roteirista).
COADJUVANTES_SEGUROS = [
    "capivara", "arara", "tucano", "mico-leão-dourado", "quati", "onça-pintada", "bicho-preguiça", "sapinho",
    "cachorro", "gato", "coelho", "ovelha", "galinha", "pintinho", "pato", "vaca", "bezerro", "porquinho",
    "cavalo", "pônei", "cabra", "elefante", "girafa", "leão", "zebra", "macaco", "urso", "panda", "pinguim",
    "coruja", "esquilo", "raposa", "ratinho", "joaninha", "abelha", "borboleta",
]

# Trechos que reprovam um coadjuvante (aquáticos, cascos, escamas e anatomias que a IA erra).
COADJUVANTES_PROIBIDOS = [
    "peixe", "boto", "golfinh", "baleia", "tubar", "tartarug", "jabuti", "cagado", "tatu", "tamandu", "iguana",
    "lagart", "jacare", "cobra", "serpente", "polvo", "caranguej", "camar", "agua-viva", "estrela-do-mar",
    "cavalo-marinho", "porco-espinho", "ourico", "aranha", "escorpi", "centopeia", "formiga", "barata",
]
