-- Feature-Test Map의 테이블과 뷰 정의.
-- 변환 명령(scripts/build.py)과 조회 스크립트(scripts/query.py)가 이 파일을 함께 사용한다.
-- 이 파일을 고치면 SKILL.md의 스키마 설명도 함께 고친다.

-- 기능 레코드(DP-1). 한 행이 기능 하나다.
CREATE TABLE feature (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  path        TEXT NOT NULL,
  parent_id   TEXT REFERENCES feature(id) DEFERRABLE INITIALLY DEFERRED,
  description TEXT NOT NULL,
  ims_ref     TEXT NOT NULL
);

-- 생성 정보(DP-4). 데이터가 아니며, 조회 스크립트의 최신성 검사에 사용한다.
CREATE TABLE build_info (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- 검증 대상인 말단 기능. 자식 항목이 없는 기능이다.
CREATE VIEW v_leaf_feature AS
SELECT f.*
FROM feature f
WHERE NOT EXISTS (SELECT 1 FROM feature c WHERE c.parent_id = f.id);

-- (상위 기능, 그 아래의 말단 기능) 쌍. 말단 기능 자신도 ancestor_id = feature_id인 행으로 포함한다.
CREATE VIEW v_feature_subtree AS
WITH RECURSIVE sub(ancestor_id, feature_id) AS (
  SELECT id, id FROM feature
  UNION ALL
  SELECT sub.ancestor_id, c.id
  FROM sub JOIN feature c ON c.parent_id = sub.feature_id
)
SELECT sub.ancestor_id, sub.feature_id
FROM sub JOIN v_leaf_feature l ON l.id = sub.feature_id;

-- 인스턴스 시나리오 레코드(DP-7). 한 행이 인스턴스 시나리오 하나다.
CREATE TABLE scenario (
  id               TEXT PRIMARY KEY,
  feature_id       TEXT NOT NULL REFERENCES feature(id),
  stimulus         TEXT NOT NULL,
  environment      TEXT NOT NULL,
  response         TEXT NOT NULL,
  response_measure TEXT NOT NULL
);
CREATE INDEX idx_scenario_feature_id ON scenario(feature_id);

-- TC 레코드(DP-2). 한 행이 TC 하나다.
-- owner는 TC를 운영하는 조직이고, platform은 TC를 실행하는 환경이다. 두 열의 조합에는 제약이 없다.
-- 허용하는 값을 추가할 때에는 아래의 CHECK와 값 목록 뷰(v_tc_owner, v_tc_platform)를 함께 고친다.
CREATE TABLE tc (
  id          INTEGER PRIMARY KEY,
  suite       TEXT NOT NULL,
  name        TEXT NOT NULL,
  source_file TEXT NOT NULL,
  owner       TEXT NOT NULL CHECK (owner IN ('sv', 'sw-dev')),
  platform    TEXT NOT NULL CHECK (platform IN ('msvp', 'hapsim')),
  UNIQUE (suite, name)
);

-- owner에 허용하는 값의 목록. 해당하는 TC가 없는 값도 분류별 집계에 행으로 나타나게 한다.
CREATE VIEW v_tc_owner AS
SELECT 'sv' AS owner UNION ALL SELECT 'sw-dev';

-- platform에 허용하는 값의 목록.
CREATE VIEW v_tc_platform AS
SELECT 'msvp' AS platform UNION ALL SELECT 'hapsim';

-- 시나리오-TC 관계 레코드(DP-3). 한 행이 'TC 하나가 인스턴스 시나리오 하나를 검증한다'는 연결 하나다.
CREATE TABLE scenario_tc (
  scenario_id TEXT    NOT NULL REFERENCES scenario(id),
  tc_id       INTEGER NOT NULL REFERENCES tc(id),
  PRIMARY KEY (scenario_id, tc_id)
);
CREATE INDEX idx_scenario_tc_tc_id ON scenario_tc(tc_id);

-- (말단 기능, 그 기능을 검증하는 TC) 쌍. 중복이 없다.
CREATE VIEW v_feature_tc AS
SELECT DISTINCT s.feature_id, r.tc_id
FROM scenario s JOIN scenario_tc r ON r.scenario_id = s.id;

-- 인스턴스 시나리오별 TC 개수. tc_count가 0이면 인스턴스 시나리오 단위의 검증 공백이다.
CREATE VIEW v_scenario_tc_count AS
SELECT s.id AS scenario_id, s.feature_id, COUNT(r.tc_id) AS tc_count
FROM scenario s LEFT JOIN scenario_tc r ON r.scenario_id = s.id
GROUP BY s.id;

-- 말단 기능별 집계. tc_count가 0이면 검증되지 않은 기능이다. 같은 TC는 한 번만 센다.
CREATE VIEW v_feature_tc_count AS
SELECT l.id AS feature_id,
  (SELECT COUNT(*) FROM scenario s WHERE s.feature_id = l.id) AS scenario_count,
  (SELECT COUNT(*) FROM v_scenario_tc_count c
    WHERE c.feature_id = l.id AND c.tc_count = 0) AS uncovered_scenario_count,
  (SELECT COUNT(*) FROM v_feature_tc ft WHERE ft.feature_id = l.id) AS tc_count
FROM v_leaf_feature l;

-- 기능별 하위 트리 집계. 묶음 기능과 말단 기능을 모두 포함한다. 같은 TC는 한 번만 센다.
CREATE VIEW v_subtree_tc_count AS
SELECT f.id AS feature_id,
  (SELECT COUNT(*) FROM v_feature_subtree st WHERE st.ancestor_id = f.id) AS leaf_count,
  (SELECT COUNT(*) FROM v_feature_subtree st
    WHERE st.ancestor_id = f.id
      AND NOT EXISTS (SELECT 1 FROM v_feature_tc ft WHERE ft.feature_id = st.feature_id)) AS uncovered_leaf_count,
  (SELECT COUNT(DISTINCT ft.tc_id) FROM v_feature_subtree st
    JOIN v_feature_tc ft ON ft.feature_id = st.feature_id
    WHERE st.ancestor_id = f.id) AS tc_count
FROM feature f;

-- 어느 인스턴스 시나리오에도 연결되지 않은 TC.
CREATE VIEW v_unlinked_tc AS
SELECT t.*
FROM tc t
WHERE NOT EXISTS (SELECT 1 FROM scenario_tc r WHERE r.tc_id = t.id);

-- 운영 조직(owner)별, 인스턴스 시나리오별 TC 개수. owner가 그 값인 TC만 센다.
-- tc_count가 0이면 그 owner의 TC로는 검증되지 않는 인스턴스 시나리오다.
CREATE VIEW v_scenario_tc_count_by_owner AS
SELECT o.owner, s.id AS scenario_id, s.feature_id,
  (SELECT COUNT(*) FROM scenario_tc r JOIN tc t ON t.id = r.tc_id
    WHERE r.scenario_id = s.id AND t.owner = o.owner) AS tc_count
FROM v_tc_owner o CROSS JOIN scenario s;

-- 운영 조직(owner)별, 말단 기능별 집계. owner가 그 값인 TC만 센다. 같은 TC는 한 번만 센다.
CREATE VIEW v_feature_tc_count_by_owner AS
SELECT o.owner, l.id AS feature_id,
  (SELECT COUNT(*) FROM scenario s WHERE s.feature_id = l.id) AS scenario_count,
  (SELECT COUNT(*) FROM v_scenario_tc_count_by_owner c
    WHERE c.owner = o.owner AND c.feature_id = l.id AND c.tc_count = 0) AS uncovered_scenario_count,
  (SELECT COUNT(*) FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
    WHERE ft.feature_id = l.id AND t.owner = o.owner) AS tc_count
FROM v_tc_owner o CROSS JOIN v_leaf_feature l;

-- 운영 조직(owner)별, 기능별 하위 트리 집계. owner가 그 값인 TC만 센다. 같은 TC는 한 번만 센다.
CREATE VIEW v_subtree_tc_count_by_owner AS
SELECT o.owner, f.id AS feature_id,
  (SELECT COUNT(*) FROM v_feature_subtree st WHERE st.ancestor_id = f.id) AS leaf_count,
  (SELECT COUNT(*) FROM v_feature_subtree st
    WHERE st.ancestor_id = f.id
      AND NOT EXISTS (SELECT 1 FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
                      WHERE ft.feature_id = st.feature_id AND t.owner = o.owner)) AS uncovered_leaf_count,
  (SELECT COUNT(DISTINCT ft.tc_id) FROM v_feature_subtree st
    JOIN v_feature_tc ft ON ft.feature_id = st.feature_id
    JOIN tc t ON t.id = ft.tc_id
    WHERE st.ancestor_id = f.id AND t.owner = o.owner) AS tc_count
FROM v_tc_owner o CROSS JOIN feature f;

-- 실행 환경(platform)별, 인스턴스 시나리오별 TC 개수. platform가 그 값인 TC만 센다.
-- tc_count가 0이면 그 platform의 TC로는 검증되지 않는 인스턴스 시나리오다.
CREATE VIEW v_scenario_tc_count_by_platform AS
SELECT o.platform, s.id AS scenario_id, s.feature_id,
  (SELECT COUNT(*) FROM scenario_tc r JOIN tc t ON t.id = r.tc_id
    WHERE r.scenario_id = s.id AND t.platform = o.platform) AS tc_count
FROM v_tc_platform o CROSS JOIN scenario s;

-- 실행 환경(platform)별, 말단 기능별 집계. platform가 그 값인 TC만 센다. 같은 TC는 한 번만 센다.
CREATE VIEW v_feature_tc_count_by_platform AS
SELECT o.platform, l.id AS feature_id,
  (SELECT COUNT(*) FROM scenario s WHERE s.feature_id = l.id) AS scenario_count,
  (SELECT COUNT(*) FROM v_scenario_tc_count_by_platform c
    WHERE c.platform = o.platform AND c.feature_id = l.id AND c.tc_count = 0) AS uncovered_scenario_count,
  (SELECT COUNT(*) FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
    WHERE ft.feature_id = l.id AND t.platform = o.platform) AS tc_count
FROM v_tc_platform o CROSS JOIN v_leaf_feature l;

-- 실행 환경(platform)별, 기능별 하위 트리 집계. platform가 그 값인 TC만 센다. 같은 TC는 한 번만 센다.
CREATE VIEW v_subtree_tc_count_by_platform AS
SELECT o.platform, f.id AS feature_id,
  (SELECT COUNT(*) FROM v_feature_subtree st WHERE st.ancestor_id = f.id) AS leaf_count,
  (SELECT COUNT(*) FROM v_feature_subtree st
    WHERE st.ancestor_id = f.id
      AND NOT EXISTS (SELECT 1 FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
                      WHERE ft.feature_id = st.feature_id AND t.platform = o.platform)) AS uncovered_leaf_count,
  (SELECT COUNT(DISTINCT ft.tc_id) FROM v_feature_subtree st
    JOIN v_feature_tc ft ON ft.feature_id = st.feature_id
    JOIN tc t ON t.id = ft.tc_id
    WHERE st.ancestor_id = f.id AND t.platform = o.platform) AS tc_count
FROM v_tc_platform o CROSS JOIN feature f;
