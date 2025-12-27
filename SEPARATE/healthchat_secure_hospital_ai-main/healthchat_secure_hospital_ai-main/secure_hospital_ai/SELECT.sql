SELECT
    p.patient_id,
    p.first_name,
    p.last_name,
    p.date_of_birth_year,
    p.gender,
    p.created_at
FROM ehr_patient AS p
WHERE p.patient_id = 'NUGWI'
LIMIT 1;
