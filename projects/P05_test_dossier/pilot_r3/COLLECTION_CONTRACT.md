# P05 R3 — Contrat de collecte, version 1

Ce contrat accompagne le protocole R2 exact `PILOT_PROTOCOL_R2.txt`. Il remplace
pour une nouvelle collecte les deux anciens gabarits de manifeste et de ledger,
sans modifier leurs archives. Aucune signature, observation ou autorisation
n'est créée par le logiciel. Le pilote demeure **PREPARED_NOT_RUN**.

## Un formulaire, des preuves conservées séparément

`collection.template.json` contient un manifeste, un registre de toutes les
tentatives, un modèle d'enregistrement et les frais communs. Copier le modèle
`record_template` dans `records` pour **chaque tentative**, réussie, rejetée,
bloquée ou abandonnée. Le modèle n'est jamais une observation. Reporter les
identifiants, jamais les noms réels, données client ou pièces confidentielles
dans un dépôt public. Le responsable garde les preuves dans la destination
privée approuvée et fixe la conservation et les accès.

Chaque pièce est nommée dans `artifacts` avec ID, chemin relatif, nombre d'octets
et SHA256. Le calculateur lit réellement les fichiers, refuse les liens
symboliques et chemins sortant de la racine, et compare tailles et empreintes.
Ces contrôles ne prouvent ni auteur, ni calibration, ni droit, ni approbation.
Ne pas remplacer les sources originales par les objets JSON du dossier P05.
Les comptes rendus d'aide, minutage, arbitrage et dépenses sont aussi des pièces.

## Entrées et seuil de départ documentaire

Pour le vrai pilote, choisir `scope=FULL_PILOT`. Les 16 missions distinctes ont
des IDs stables : 4 DEVELOPMENT et 12 RESERVE, au moins 3 familles. Chaque
mission lie famille, contrat approuvé indépendamment des exports, mêmes pièces
A0/A1 et opérateurs désignés. La réserve alterne six A0 d'abord et six A1
d'abord; chacun des deux opérateurs réalise six A0 et six A1 sur la réserve.
L'arbitre est distinct des opérateurs et inscrit la qualité avant de voir les
temps. Le gardien est distinct des opérateurs; il peut être l'arbitre si la
séparation des réponses et l'aveuglement des méthodes restent assurés.

Les références d'autorisation documentaire, de droits sur les données, de plan
comparatif et de gel doivent pointer vers de vraies pièces disponibles. Le
manifeste nomme détenteur des données, base d'usage, destination privée et règle
de conservation. Les sources, contrats, codes A0/A1, ordre et règle d'absence
sont figés avant ouverture de la réserve. Les droits, informations, outillage,
budgets et aides disponibles sont équivalents; aucune méthode ne voit la sortie
de l'autre. A0 reste ingénieur compétent + script indépendant; A1 adaptateur
déterministe + revue humaine. Aucun agent n'est nécessaire.

`DECLARATIONS_COMPLETE_HUMAN_SIGNOFF_REQUIRED` signifie seulement que le dossier
des prérequis est renseigné; le responsable vérifie les pièces et signe avant
départ. Le logiciel ne recrute pas les personnes, ne prouve pas leur compétence
ou l'indépendance des missions et n'autorise aucun matériel. Toute source ou
autorisation absente impose BLOCKED_INPUTS. Le mode `SYNTHETIC_PAIR` est réservé
à l'exemple synthétique et n'est jamais un raccourci pour un pilote réel.
Ce sous-kit fournit une paire d'exemple et huit régressions documentaires
strictement synthétiques décrites dans le README. Les six contrôles historiques
restent dans leurs reçus antérieurs et ne sont pas distribués ici. Les
régressions fabriquent des copies portant OBSERVED_DECLARATIONS ou TEMPLATE
pour exercer ces branches ; elles ne créent aucune observation réelle.

## Minutes humaines, machine et calendrier

Chaque événement humain a un `event_id` unique dans toute la collecte, un
`actor_id`, une catégorie, `active_seconds` mesurés, un coût horaire
`hourly_minor`, et `record_ref` vers le relevé. Les 11 catégories obligatoires
sont preparation, installation, learning, mapping, investigation, review,
correction, support, post_transfer_support, maintenance et arbitration. Même
une absence de temps doit être explicitement enregistrée et justifiée par la
pièce; `null` ou catégorie absente n'est jamais zéro.

Les segments d'une même personne ne se chevauchent pas. Les aides, gardiens et
arbitres ont leurs propres événements et taux; plusieurs personnes travaillant
simultanément peuvent légitimement cumuler plus de temps actif que le délai
écoulé. Les IDs uniques empêchent de recopier le même événement; le calculateur
ne détecte pas des segments physiques dupliqués sous de nouveaux IDs. La revue
humaine compare les relevés originaux.

`support` couvre avant transfert; `post_transfer_support` couvre après
transfert. L'objet `assistance` conserve demandes, liste des événements d'aide
déjà comptés et complétude. Il n'ajoute aucun coût une deuxième fois. Une aide
déclarée sans événement correspondant ou une collecte d'aide incomplète laisse
le coût UNKNOWN. Les fenêtres de coût et de suivi doivent être closes; le
protocole conserve son suivi J+14, seulement si autorisé. Aucune relance n'est
lancée par cet outil.

`machine_seconds`, `calendar_elapsed_seconds` et `waiting_calendar_seconds`
sont observés séparément. Ils peuvent se chevaucher; ne pas les additionner au
temps humain, en déduire un coût salarial ou transformer une attente supprimée
en économie. Le relevé est conservé dans `timing_ref`. Le logiciel préserve ces
champs dans le fichier d'entrée et les joint au résultat de chaque tentative.

## Coûts complets, sans imputation cachée

Les événements cash distincts couvrent licenses, machine_resources,
capital_calibration, actual_liability, taxes et other. `amount_minor` est un
entier dans une devise déclarée à 100 unités mineures par unité; `hourly_minor`
est le coût horaire dans ces mêmes unités. Une facture/allocation ne figure
qu'une fois. Les hypothèses de pertes ou risques futurs de l'ancien champ
`expected_loss_liability_eur` ne deviennent pas des dépenses observées:
les obligations non chiffrées sont dans `unpriced_obligations` et interdisent
le gain complet. Zéro est une absence explicitement documentée, pas un défaut.

Coût humain = somme(secondes actives × coût horaire / 3600). Les montants et
ratios sont calculés en fractions exactes; l'arrondi d'affichage ne sert pas au
calcul du pourcentage. Les frais additionnels sont ajoutés une seule fois.
Installation et apprentissage du développement sont conservés dans les 4
missions DEVELOPMENT, séparés des 12 RESERVE et inclus une seule fois au total.
Il n'existe plus de `setup_allocated` ajouté à la même installation.

Les dépenses communes non propres à une méthode vont dans `shared_cost` une
seule fois. La convention limitée choisie ici est moitié A0, moitié A1, avec
référence d'approbation figée avant comparaison. Le montant commun est aussi
rapporté séparément. Cette convention sert à la comparaison documentaire de ce
pilote; elle n'établit pas le coût de revient d'un futur service. Ne pas cacher
une aide spécifique à A1 parmi les frais communs. Une autre convention demande
un autre contrat, pas un changement rétroactif sur la réserve.

Un taux, temps, frais, aide, obligation, fenêtre ou population de tentatives
incomplet laisse le gain UNKNOWN. Le registre attendu et la liste effective des
tentatives doivent correspondre exactement, ordre compris. Le coût garde les
rejets et abandons. Un simple sous-total connu n'est pas un coût complet.

## Qualité et gain admissible

L'arbitre renseigne états documentaire et mesure séparément, réception/rejet/
abandon et raison, faux READY, faux PASS, rejet injustifié, champ perdu/inventé,
incohérence manquée, clarification et reprise. Une réception documentaire
READY_FOR_REVIEW/FAIL est possible. Le calculateur consomme les constatations
d'arbitrage; il ne détecte pas lui-même un faux READY dans l'export OpenHTF.

Arrêt critique immédiat conservé même si une tentative ultérieure corrige le
dossier : faux READY sur identité/population/limite, valeur ou preuve inventée,
action instrumentale non autorisée, source/droits manquants ou divulgation hors
périmètre. Coûts partiels restent descriptifs; gain admissible UNKNOWN.

Gain = 100 × (coût A0 − coût A1) / coût A0, seulement si A0 > 0, coûts complets,
conditions comparables, qualité A1 au moins égale et ensemble non vide de
missions reçues identique entre méthodes. Cette dernière règle conservatrice
évite de créditer une abstention totale ou des livraisons différentes. Si la
réception diffère, rapporter coûts et qualité séparément, sans pourcentage.
Les mauvais indicateurs qualité ne sont pas compensés par le prix. Une baisse
de coût négative est conservée. La promesse de 20 % est abandonnée si le seuil
n'est pas atteint, si les coûts manquent ou si la qualité est inférieure.
L'outil n'attribue jamais automatiquement une validation de cette promesse.
Les six indicateurs de non-infériorité sont faux READY, faux PASS, rejets
injustifiés, champs perdus, champs inventés et incohérences non signalées.
Clarifications et reprises restent visibles et leur travail est compté;
leur nombre seul n'est pas automatiquement une dégradation de qualité.

## Frontières et sortie

Le profil d'entrée demeure 1 phase / 1 scalaire pour l'adaptateur public;
identités, unités, limites et révision restent dans son contrat. Le présent
outil additionne la collecte, ne remplace ni l'adaptateur, ni le script A0,
ni l'arbitrage, ni une certification matérielle. Une falsification cohérente
peut satisfaire des contrôles documentaires. `material_release_authorized`
reste toujours false. Les exports natifs historiques sont synthétiques.

Code retour 0: évaluation effectuée, y compris un gain UNKNOWN; 3: arrêt
critique/intégrité; 2: entrée invalide. Lire le JSON, jamais le seul code retour.
Le résultat inclut l'empreinte de l'entrée et du calculateur. Conserver entrée,
pièces, stdout, stderr et code retour ensemble. Aucun résultat de la paire d'exemple ou des huit
régressions synthétiques ne représente une mission de la réserve, une mesure humaine,
un client, une économie observée ou une validation physique.

## Rapprochement explicite des anciens gabarits

| Ancien champ R2 | Destination unique R3 / règle |
| --- | --- |
| data_owner, rights_basis, approved_private_destination | manifest.data_rights, avec pièce de droits référencée |
| pilot_manager et separate_authorization_received | pièce pilot_authorization_ref identifiant le responsable; un booléen ne remplace pas l'autorisation |
| operator_A/B, blind_human_reviewer, reserve_guardian | manifest.roles et affectations A0/A1 par mission |
| approved_contracts, client_exports | artifacts + contrat, approbation et sources par mission; octets originaux conservés |
| familles, stations, versions logiciel/firmware, unités, limites | contrat de chaque mission et pièces natives P05; aucune duplication/inférence dans le calculateur de coûts |
| clock_provenance, calibration_provenance | pièces natives/contrat et arbitrage; leur SHA ne valide ni horloge ni calibration |
| frozen_code_sha256_A0/A1, freeze_time_utc | manifest.code_sha256 et pièce freeze_ref datée, avant réserve |
| reserve_schedule | manifest.missions, avec quatre missions DEVELOPMENT ajoutées et registre de toutes les tentatives |
| active_minutes.preparation/mapping/investigation/review/correction/maintenance | human_events, mêmes catégories, secondes observées et acteur/taux par événement |
| active_minutes.training | human_events.learning |
| active_minutes.setup_allocated | installation originale documentée une fois; ne pas recopier une allocation déjà incluse ailleurs |
| active_minutes.support, post_transfer_support_minutes | support avant transfert / post_transfer_support après transfert, sans recouvrement |
| hourly_cost_eur | hourly_minor propre à chaque acteur, devise déclarée; taux absent = UNKNOWN |
| machine_seconds, waiting_calendar_minutes | machine_seconds et waiting_calendar_seconds; conversion d'unité explicite seulement |
| run_started_utc, run_ended_utc | relevé original identifié par timing_ref; calendar_elapsed_seconds reste observé, pas somme de postes |
| incremental_cash_eur, license_cost_eur, capital_calibration_incremental_eur, taxes_eur | cash_events dans une catégorie exclusive, avec pièce et ID; ne pas compter une même facture deux fois |
| expected_loss_liability_eur | hypothèse/non-chiffré dans unpriced_obligations; actual_liability seulement si charge réellement établie par pièce |
| human_receipt, abandoned, abandon_reason | quality.outcome et reason, pour toutes les tentatives conservées |
| false_ready_count, false_pass_count, lost_fields_count, invented_fields_count | quality: mêmes faits, plus domaine critique, rejets injustifiés et incohérences non signalées |
| clarification_count, corrections/reprises | quality.clarifications/reworks; durée et coût déjà dans les événements, pas addition d'un forfait |
| measured_client_demand | reste hors calcul de coût; aucune demande n'est déduite d'un formulaire ou d'un gain SYNTHETIC |
| material_release_authorized | false, invariant sans exception |

Le calculateur ne migre pas automatiquement un ancien ledger : les informations
manquantes (acteur d'aide, frais communs, tentatives, droits) doivent être
retrouvées dans les preuves ou rester UNKNOWN. Une conversion de clés ne peut
pas fabriquer les observations qui n'ont jamais été recueillies.
