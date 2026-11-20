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
