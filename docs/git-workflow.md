# Git Workflow

## Mục đích

Tài liệu này quy định quy trình làm việc với Git trong dự án nhằm:

* Đồng nhất cách làm việc giữa các thành viên.
* Giảm xung đột khi phát triển song song.
* Đảm bảo lịch sử commit rõ ràng và dễ truy vết.
* Hỗ trợ AI Coding Assistant tạo branch và commit đúng quy chuẩn.

---

# 1. Gitflow

Dự án sử dụng mô hình Gitflow với các nhánh chính sau:

## main

* Chứa mã nguồn ổn định, sẵn sàng triển khai.
* Không commit trực tiếp vào nhánh này.
* Chỉ được cập nhật thông qua Pull Request đã được review.

## develop

* Chứa phiên bản phát triển mới nhất.
* Là nhánh gốc để tạo các feature branch.
* Không commit trực tiếp vào nhánh này.

---

# 2. Các loại nhánh

## feature

Dùng để phát triển tính năng mới.

Ví dụ:

```bash
feature/user-authentication
feature/document-ingestion
feature/rag-chatbot
```

Tạo từ:

```bash
develop
```

Merge về:

```bash
develop
```

---

## bugfix

Dùng để sửa lỗi trong quá trình phát triển.

Ví dụ:

```bash
bugfix/fix-login-validation
bugfix/fix-file-upload
```

Tạo từ:

```bash
develop
```

Merge về:

```bash
develop
```

---

## hotfix

Dùng để xử lý lỗi khẩn cấp trên môi trường production.

Ví dụ:

```bash
hotfix/fix-production-crash
hotfix/fix-auth-token-expired
```

Tạo từ:

```bash
main
```

Merge về:

```bash
main
develop
```

---

## release

Dùng để chuẩn bị phát hành phiên bản mới.

Ví dụ:

```bash
release/v1.0.0
release/v1.1.0
```

Tạo từ:

```bash
develop
```

Merge về:

```bash
main
develop
```

---

# 3. Quy tắc đặt tên branch

Cú pháp:

```text
<type>/<mô-tả-ngắn>
```

## Quy tắc

* Sử dụng chữ thường.
* Sử dụng dấu `-` để ngăn cách từ.
* Tên branch cần mô tả rõ mục đích.
* Không sử dụng tiếng Việt có dấu.
* Không sử dụng tên cá nhân.

## Ví dụ đúng

```bash
feature/add-user-management
feature/document-parser

bugfix/fix-null-pointer

hotfix/fix-memory-leak

docs/update-readme

refactor/auth-service
```

## Ví dụ không đúng

```bash
feature1
new-feature
fixbug
tuan-branch
update-code
test123
```

---

# 4. Quy tắc Commit Message

Dự án sử dụng chuẩn Conventional Commits.

## Cú pháp

```text
<type>(scope): <description>
```

Trong đó:

* type: loại thay đổi.
* scope: thành phần bị ảnh hưởng (không bắt buộc).
* description: mô tả ngắn gọn.

Ví dụ:

```bash
feat(auth): add jwt authentication

fix(parser): handle malformed pdf metadata

refactor(chunking): simplify chunk creation logic

docs(readme): update installation guide
```

---

## Các loại commit

### feat

Thêm tính năng mới.

```bash
feat(chat): support streaming response
```

### fix

Sửa lỗi.

```bash
fix(auth): handle expired access token
```

### refactor

Tái cấu trúc mã nguồn nhưng không thay đổi hành vi.

```bash
refactor(service): extract validation logic
```

### docs

Cập nhật tài liệu.

```bash
docs(readme): add local development guide
```

### test

Thêm hoặc cập nhật test.

```bash
test(api): add ingestion endpoint tests
```

### chore

Công việc bảo trì hoặc cấu hình.

```bash
chore(deps): upgrade langchain version
```

### style

Chỉnh sửa format code, không thay đổi logic.

```bash
style(api): apply linting fixes
```

### perf

Tối ưu hiệu năng.

```bash
perf(search): improve vector retrieval latency
```

### ci

Thay đổi liên quan CI/CD.

```bash
ci(github-actions): add deployment workflow
```

---

## Quy tắc viết commit message

### Nên

```bash
feat(auth): add login endpoint

fix(upload): validate file size

docs(api): update endpoint examples
```

### Không nên

```bash
update

fix bug

done

wip

final version

commit again
```

---

# 5. Pull Request

## Tên Pull Request

Sử dụng cùng format với commit message:

```bash
feat(auth): add login endpoint

fix(upload): validate file size
```

---

## Checklist trước khi tạo Pull Request

* [ ] Đã pull code mới nhất từ nhánh đích.
* [ ] Build thành công.
* [ ] Test thành công.
* [ ] Không còn code debug hoặc log tạm.
* [ ] Đã cập nhật tài liệu nếu cần.
* [ ] Đã tự review thay đổi của bản thân.

---

# 6. Quy trình làm việc khuyến nghị

Tạo nhánh mới:

```bash
git checkout develop
git pull origin develop
git checkout -b feature/document-ingestion
```

Commit:

```bash
git add .
git commit -m "feat(ingestion): add pdf parser"
```

Đẩy lên remote:

```bash
git push origin feature/document-ingestion
```

Tạo Pull Request:

```text
feature/document-ingestion
→ develop
```

Sau khi được review và phê duyệt, Pull Request mới được merge.

---

# 7. Hướng dẫn dành cho AI Coding Assistant

Khi thực hiện thay đổi mã nguồn:

* Không commit trực tiếp vào `main` hoặc `develop`.
* Luôn đề xuất branch name theo quy tắc của dự án.
* Luôn đề xuất commit message theo chuẩn Conventional Commits.
* Ưu tiên thay đổi nhỏ, rõ ràng và có mục tiêu cụ thể.
* Cập nhật test khi thay đổi logic nghiệp vụ.
* Cập nhật tài liệu khi bổ sung tính năng mới.
* Giữ nguyên kiến trúc hiện có nếu không được yêu cầu thay đổi.

Khi hoàn thành một tác vụ, AI Assistant nên đề xuất:

```text
Branch:
feature/example-feature

Commit:
feat(scope): short description
```
