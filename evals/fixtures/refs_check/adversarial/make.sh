#!/bin/bash
# Synthetic .bib fixtures for refs_check.py. Real identifiers are used on purpose (network needed).
set -e
B=${1:-$(cd "$(dirname "$0")" && pwd)}   # output folder (default: this folder)
cd "$B"

mkdir -p subtitles && cat > subtitles/refs.bib <<'EOF'
@book{s1_subtitle_dropped, author={Christopher D. Manning and Prabhakar Raghavan and Hinrich Sch{\"u}tze}, title={Introduction to Information Retrieval}, publisher={Cambridge University Press}, year={2008}, doi={10.1017/CBO9780511809071}}
@book{s2_subtitle_added, author={Christopher D. Manning and others}, title={Introduction to Information Retrieval: An Online Edition}, publisher={Cambridge University Press}, year={2008}, doi={10.1017/CBO9780511809071}}
@article{s3_two_word_subset, author={E. F. Codd}, title={Data Banks}, journal={Commun. ACM}, year={1970}, doi={10.1145/362384.362685}}
@inproceedings{s4_overlap_only, author={Kaiming He and others}, title={Deep Learning}, booktitle={CVPR}, year={2016}, doi={10.1109/CVPR.2016.90}}
@inproceedings{s5_chapter_doi_book_title, author={Leonid Boytsov and Bilegsaikhan Naidan}, title={Similarity Search and Applications}, booktitle={SISAP}, year={2013}, doi={10.1007/978-3-642-41062-8_28}}
EOF
cat > subtitles/EXPECTED.md <<'EOF'
# subtitles: title similarity against Crossref
MUST NOT report: s1, s2 (subtitle added: containment 0.9 passes).
MUST report FAIL "DOI points to another work": s5 (the book title with a chapter DOI).
Expected weaknesses: s3 "Data Banks" and s4 "Deep Learning" pass, because any two words contained in the real title give 0.9
(similar(): containment is computed on min(|A|,|B|) >= 2). A wrong-but-overlapping title is never caught.
EOF

mkdir -p names-accents && cat > names-accents/refs.bib <<'EOF'
@article{n1_german_escaped, author={G{\"o}del, Kurt}, title={{\"U}ber formal unentscheidbare S{\"a}tze der Principia Mathematica und verwandter Systeme I}, journal={Monatshefte f{\"u}r Mathematik und Physik}, volume={38}, year={1931}, doi={10.1007/BF01700692}}
@article{n2_translated_title, author={G{\"o}del, Kurt}, title={On Formally Undecidable Propositions of Principia Mathematica and Related Systems I}, journal={Monatshefte f{\"u}r Mathematik und Physik}, volume={38}, year={1931}, doi={10.1007/BF01700692}}
@article{n3_braces_colon, author={Devlin, Jacob and Chang, Ming-Wei and Lee, Kenton and Toutanova, Kristina}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, journal={arXiv preprint arXiv:1810.04805}, year={2018}, eprint={1810.04805}, archivePrefix={arXiv}}
@misc{n4_protected_letter, author={Matthijs Douze and Alexandr Guzhva and Chengqi Deng and Jeff Johnson and Gergely Szilvasy and Pierre-Emmanuel Mazar{\'e} and Maria Lomeli and Lucas Hosseini and Herv{\'e} J{\'e}gou}, title={The {F}aiss library}, year={2024}, eprint={2401.08281}, archivePrefix={arXiv}}
@inproceedings{n5_math_in_title, author={Alexandr Andoni and Piotr Indyk}, title={Near-Optimal Hashing Algorithms for Approximate Nearest Neighbor in High Dimensions}, booktitle={FOCS}, year={2006}, doi={10.1109/FOCS.2006.49}}
EOF
cat > names-accents/EXPECTED.md <<'EOF'
# names-accents: LaTeX-escaped accents, braces, translated titles
MUST NOT report: n1 (escaped umlauts fold to the Crossref title), n3, n4, n5.
Expected false positive: n2 (the English translation of a German title) -> FAIL "DOI points to another work"; needs a
"title in another language" escape (e.g. CHECK when the Crossref title has no common words at all AND the DOI resolves).
EOF

mkdir -p corporate-datasets && cat > corporate-datasets/refs.bib <<'EOF'
@misc{c1_openai, author={{OpenAI}}, title={{GPT-4} Technical Report}, year={2023}, eprint={2303.08774}, archivePrefix={arXiv}}
@misc{c2_gemini_team, author={{Gemini Team} and others}, title={Gemini: A Family of Highly Capable Multimodal Models}, year={2023}, eprint={2312.11805}, archivePrefix={arXiv}}
@software{c3_zenodo_ok, author={{The scikit-learn developers}}, title={scikit-learn}, year={2024}, doi={10.5281/zenodo.591564}}
@misc{c4_zenodo_wrong_title, author={Nobody}, title={ImageNet Large Scale Visual Recognition Challenge dataset}, year={2024}, doi={10.5281/zenodo.591564}}
@misc{c5_repo_only, title={Faiss}, howpublished={\url{https://github.com/facebookresearch/faiss}}, year={2024}}
EOF
cat > corporate-datasets/EXPECTED.md <<'EOF'
# corporate authors, software/dataset DOIs (DataCite, not Crossref)
MUST NOT report: c1, c2, c3, c5.
Expected false negative: c4 (a Zenodo DOI with a wrong title): DataCite DOIs are only checked for existence
(doi.org handle), never for the title. Fix: query https://api.datacite.org/dois/<doi> when Crossref gives 404.
EOF

mkdir -p reports-books && cat > reports-books/refs.bib <<'EOF'
@techreport{r1_techreport, author={Lawrence Page and Sergey Brin and Rajeev Motwani and Terry Winograd}, title={The PageRank Citation Ranking: Bringing Order to the Web}, institution={Stanford InfoLab}, number={1999-66}, year={1999}}
@book{r2_book_doi, author={Christopher D. Manning and Prabhakar Raghavan and Hinrich Sch{\"u}tze}, title={Introduction to Information Retrieval}, publisher={Cambridge University Press}, year={2008}, doi={10.1017/CBO9780511809071}}
@book{r3_book_isbn, author={Donald E. Knuth}, title={The Art of Computer Programming, Volume 3: Sorting and Searching}, publisher={Addison-Wesley}, year={1998}, isbn={0-201-89685-0}}
@incollection{r4_chapter, author={Leonid Boytsov and Bilegsaikhan Naidan}, title={Engineering Efficient and Effective Non-metric Space Library}, booktitle={Similarity Search and Applications}, year={2013}, doi={10.1007/978-3-642-41062-8_28}}
@phdthesis{r5_thesis, author={Sergey Brin}, title={Extracting Patterns and Relations from the World Wide Web}, school={Stanford}, year={1999}}
EOF
cat > reports-books/EXPECTED.md <<'EOF'
# tech reports, books, theses
MUST NOT report anything (own checks); r1, r3, r5 have no identifier, so only RefChecker can say anything about them.
EOF

mkdir -p arxiv-ids && cat > arxiv-ids/refs.bib <<'EOF'
@misc{a1_old_style_eprint, author={Oliver Lassila}, title={Using Structural Metadata to Localize Experience of Digital Content}, year={2001}, eprint={cs/0112017}, archivePrefix={arXiv}}
@article{a2_old_style_in_journal, author={Oliver Lassila}, title={Using Structural Metadata to Localize Experience of Digital Content}, journal={arXiv preprint cs.DL/0112017}, year={2001}}
@misc{a3_versioned, author={Edward J. Hu and others}, title={{LoRA}: Low-Rank Adaptation of Large Language Models}, year={2021}, eprint={2106.09685v3}, archivePrefix={arXiv}}
@misc{a4_url_only, author={Ashish Vaswani and others}, title={Attention Is All You Need}, year={2017}, url={https://arxiv.org/abs/1706.03762v7}}
@misc{a5_doi_48550, author={Jacob Devlin and others}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, year={2018}, doi={10.48550/arXiv.1810.04805}}
@misc{a6_nonexistent, author={Nobody}, title={A Paper That Does Not Exist}, year={2025}, eprint={2501.99999}, archivePrefix={arXiv}}
@misc{a7_wrong_paper, author={Jacob Devlin and others}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, year={2018}, eprint={1706.03762}, archivePrefix={arXiv}}
@misc{a8_note_only, author={Yu. A. Malkov and D. A. Yashunin}, title={Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs}, year={2016}, note={arXiv:1603.09320}}
@article{a9_dblp_corr_volume, author={Tomas Mikolov and Kai Chen and Greg Corrado and Jeffrey Dean}, title={Efficient Estimation of Word Representations in Vector Space}, journal={CoRR}, volume={abs/1301.3781}, year={2013}}
@article{a10_dblp_corr_wrong_volume, author={Tomas Mikolov and others}, title={Efficient Estimation of Word Representations in Vector Space}, journal={CoRR}, volume={abs/1706.03762}, year={2013}}
EOF
cat > arxiv-ids/EXPECTED.md <<'EOF'
# arXiv identifiers in every form
MUST report FAIL: a6 (ID does not exist), a7 (ID is "Attention Is All You Need", not BERT).
MUST report CHECK "published version exists": a8 (TPAMI 2020), a9 (ICLR 2013 workshop, if DBLP lists it).
MUST NOT report: a1 (old-style id in eprint), a3, a4, a5, a9.
Expected bugs: a1 -> FAIL "does not exist" (arxiv_titles() keys the API answer by the last path component, "0112017v1",
so old-style ids never match); a2 old-style id in the journal field is not recognised (regex wants NNNN.NNNNN);
a9/a10 DBLP exports put the id in volume={abs/...}: not read, so a10's wrong id is missed and a9 is not even checked.
EOF

mkdir -p biblatex && cat > biblatex/refs.bib <<'EOF'
@online{b1_online, author={Edward J. Hu and others}, title={{LoRA}: Low-Rank Adaptation of Large Language Models}, date={2021-06-17}, eprinttype={arxiv}, eprint={2106.09685}, eprintclass={cs.CL}}
@article{b2_journaltitle_corr, author={Yu. A. Malkov and D. A. Yashunin}, title={Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs}, journaltitle={CoRR}, volume={abs/1603.09320}, date={2016}}
@software{b3_software, author={{The scikit-learn developers}}, title={scikit-learn}, version={1.5.0}, date={2024}, doi={10.5281/zenodo.591564}}
@dataset{b4_dataset_wrong_title, author={Nobody}, title={A dataset this DOI does not name}, date={2024}, doi={10.5281/zenodo.591564}}
@thesis{b5_thesis, author={Sergey Brin}, title={Extracting Patterns and Relations from the World Wide Web}, institution={Stanford}, type={phdthesis}, date={1999}}
@online{b6_eprint_wrong, author={Nobody}, title={A Title That Is Not The Transformer Paper}, date={2017}, eprinttype={arxiv}, eprint={1706.03762}}
EOF
cat > biblatex/EXPECTED.md <<'EOF'
# biblatex field names (date, journaltitle, eprinttype, @online/@software/@dataset/@thesis)
MUST report FAIL: b6 (arXiv ID points to another paper).
MUST report CHECK "published version exists": b2 (HNSW, TPAMI 2020).
MUST NOT report: b1, b3, b5.
Expected bugs: b2 is not seen as a preprint (is_preprint() reads journal, not journaltitle) and its id sits in volume;
b4 wrong title on a DataCite DOI is missed (see corporate-datasets).
EOF

mkdir -p doi-forms && cat > doi-forms/refs.bib <<'EOF'
@inproceedings{d1_mixed_case, author={Kaiming He and Xiangyu Zhang and Shaoqing Ren and Jian Sun}, title={Deep Residual Learning for Image Recognition}, booktitle={CVPR}, year={2016}, doi={10.1109/CVPR.2016.90}}
@article{d2_https_prefix, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, journal={Commun. ACM}, year={1970}, doi={https://doi.org/10.1145/362384.362685}}
@article{d3_dx_prefix, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, journal={Commun. ACM}, year={1970}, doi={http://dx.doi.org/10.1145/362384.362685}}
@article{d4_doi_colon_prefix, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, journal={Commun. ACM}, year={1970}, doi={doi:10.1145/362384.362685}}
@article{d5_trailing_dot, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, journal={Commun. ACM}, year={1970}, doi={10.1145/362384.362685.}}
@inproceedings{d6_lower_case, author={Kaiming He and others}, title={Deep Residual Learning for Image Recognition}, booktitle={CVPR}, year={2016}, doi={10.1109/cvpr.2016.90}}
@misc{d7_doi_only_in_url, author={Jacob Devlin and others}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, year={2016}, url={https://doi.org/10.1109/CVPR.2016.90}}
@article{d8_nonexistent, author={Nobody}, title={Nothing}, journal={Nowhere}, year={2020}, doi={10.1145/9999999.9999999}}
@incollection{d9_escaped_underscore, author={Leonid Boytsov and Bilegsaikhan Naidan}, title={Engineering Efficient and Effective Non-metric Space Library}, booktitle={SISAP}, year={2013}, doi={10.1007/978-3-642-41062-8\_28}}
@inproceedings{d10_acl_anthology, author={Jacob Devlin and others}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, booktitle={NAACL}, year={2019}, doi={10.18653/v1/N19-1423}}
EOF
cat > doi-forms/EXPECTED.md <<'EOF'
# DOI spellings
MUST report FAIL "does not resolve": d8. d5 (trailing dot) may be reported as not resolving: acceptable, the printed DOI is broken.
MUST NOT report: d1, d2, d3, d6, d9, d10.
Expected bugs: d4 "doi:" prefix is not stripped -> FAIL "does not resolve" (false positive);
d7 a DOI that only appears in url= is never checked, so its wrong target (ResNet, cited as BERT) is missed.
EOF

mkdir -p strings-crossref && cat > strings-crossref/refs.bib <<'EOF'
@comment{ a comment entry that BibTeX ignores }
@preamble{ "\newcommand{\noopsort}[1]{} " }
@string{sigir22 = {Proceedings of the 45th International ACM SIGIR Conference on Research and Development in Information Retrieval}}
@string{sisap = "Similarity Search and Applications"}
@inproceedings{x1_string_booktitle, author={Thibault Formal and Carlos Lassance and Benjamin Piwowarski and St{\'e}phane Clinchant}, title={From Distillation to Hard Negative Sampling: Making Sparse Neural {IR} Models More Effective}, booktitle=sigir22, year={2022}, doi={10.1145/3477495.3531857}}
@inproceedings{x2_crossref_child, author={Leonid Boytsov and Bilegsaikhan Naidan}, title={Engineering Efficient and Effective Non-metric Space Library}, pages={280--293}, doi={10.1007/978-3-642-41062-8_28}, crossref={x3_proc}}
@proceedings{x3_proc, title=sisap, booktitle=sisap, year={2013}, publisher={Springer}}
@inproceedings{x4_concat, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, booktitle={Commun. ACM} # " " # {13(6)}, year={1970}, doi={10.1145/362384.362685}}
EOF
cat > strings-crossref/EXPECTED.md <<'EOF'
# @string, @comment, @preamble, crossref inheritance, # concatenation
MUST NOT report anything on x1, x2, x4 (own checks). x3 is a @proceedings parent: if a .tex cites only x2, BibTeX pulls x3 in,
but refs_check's cited filter drops it, so RefChecker sees x2 with a dangling crossref (check what it says).
Also: form_check's "inproceedings without booktitle" fires on x2 (booktitle inherited through crossref).
Field parsing: x4's concatenated booktitle ({...} # " " # {...}) is read as the first piece only.
EOF

mkdir -p preprint-title && cat > preprint-title/refs.bib <<'EOF'
@article{p1_title_changed_when_published, author={Thibault Formal and Carlos Lassance and Benjamin Piwowarski and St{\'e}phane Clinchant}, title={{SPLADE} v2: Sparse Lexical and Expansion Model for Information Retrieval}, journal={arXiv preprint arXiv:2109.10086}, year={2021}}
@article{p2_same_title_published, author={Yu. A. Malkov and D. A. Yashunin}, title={Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs}, journal={arXiv preprint arXiv:1603.09320}, year={2016}}
@article{p3_bert_arxiv, author={Jacob Devlin and Ming-Wei Chang and Kenton Lee and Kristina Toutanova}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, journal={arXiv preprint arXiv:1810.04805}, year={2018}}
@misc{p4_never_published, author={Matthijs Douze and others}, title={The Faiss library}, year={2024}, eprint={2401.08281}, archivePrefix={arXiv}}
@misc{p5_published_cited_correctly, author={Jacob Devlin and others}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, booktitle={NAACL-HLT}, year={2019}, doi={10.18653/v1/N19-1423}}
EOF
cat > preprint-title/EXPECTED.md <<'EOF'
# preprints with a published version
MUST report CHECK "published version exists": p2 (TPAMI 2020), p3 (NAACL 2019).
MUST NOT report: p4 (no published version known), p5 (already the published version).
Expected false negative: p1 (SPLADE v2 was published at SIGIR 2022 under another title): the DBLP lookup is by exact
normalized title. RefChecker or an arXiv "journal-ref"/DOI lookup (arXiv API returns <arxiv:doi> and <arxiv:journal_ref>
when the authors set them) would catch part of these at zero extra cost: the arXiv feed is already fetched.
EOF

mkdir -p duplicates && cat > duplicates/refs.bib <<'EOF'
@article{u1_bert, author={Jacob Devlin and Ming-Wei Chang and Kenton Lee and Kristina Toutanova}, title={{BERT}: Pre-training of Deep Bidirectional Transformers for Language Understanding}, journal={arXiv preprint arXiv:1810.04805}, year={2018}, eprint={1810.04805}, archivePrefix={arXiv}}
@inproceedings{u2_bert_again, author={Jacob Devlin and Ming-Wei Chang and Kenton Lee and Kristina Toutanova}, title={{BERT}: Pre-training of deep bidirectional transformers for language understanding}, booktitle={NAACL}, year={2019}, eprint={1706.03762}, archivePrefix={arXiv}}
@article{u3_same_key, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, journal={Commun. ACM}, year={1970}, doi={10.1145/362384.362685}}
@article{u3_same_key, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, journal={Commun. ACM}, year={1970}, doi={10.1145/9999999.9999999}}
EOF
cat > duplicates/EXPECTED.md <<'EOF'
# duplicate entries
MUST report FAIL: u2 (its eprint is the Transformer paper, not BERT).
MUST report CHECK published version: u1.
Expected weaknesses: the second u3 (same key, bad DOI) is ignored because the first key wins, which matches BibTeX, but no
"repeated key" finding is produced here or in form_check (BibTeX only warns in the .blg). With RefChecker, u1 and u2 have
the same normalized title, so by_title maps both records to u1: any RefChecker finding about u2 is attributed to u1.
EOF

mkdir -p refchecker-small && cat > refchecker-small/refs.bib <<'EOF'
@article{k1_correct, author={E. F. Codd}, title={A Relational Model of Data for Large Shared Data Banks}, journal={Communications of the ACM}, volume={13}, number={6}, pages={377--387}, year={1970}, doi={10.1145/362384.362685}}
@inproceedings{k2_wrong_authors, author={Yoshua Bengio and Geoffrey E. Hinton and Andrew Y. Ng}, title={Deep Residual Learning for Image Recognition}, booktitle={2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)}, pages={770--778}, year={2016}}
@misc{k3_corporate, author={{OpenAI}}, title={{GPT-4} Technical Report}, year={2023}, eprint={2303.08774}, archivePrefix={arXiv}}
@article{k4_accents, author={G{\"o}del, Kurt}, title={{\"U}ber formal unentscheidbare S{\"a}tze der Principia Mathematica und verwandter Systeme I}, journal={Monatshefte f{\"u}r Mathematik und Physik}, volume={38}, pages={173--198}, year={1931}, doi={10.1007/BF01700692}}
@inproceedings{k5_crossref_child, author={Leonid Boytsov and Bilegsaikhan Naidan}, title={Engineering Efficient and Effective Non-metric Space Library}, pages={280--293}, doi={10.1007/978-3-642-41062-8_28}, crossref={k6_proc}}
@proceedings{k6_proc, title={Similarity Search and Applications}, booktitle={Similarity Search and Applications}, year={2013}, publisher={Springer}}
EOF
cat > refchecker-small/EXPECTED.md <<'EOF'
# RefChecker run (slow): corporate author, LaTeX accents, crossref child
MUST report CHECK: k2 (wrong authors).
MUST NOT report: k1, k3 (corporate author "OpenAI"), k4 (accented German title), k5/k6 (crossref).
EOF
echo done
