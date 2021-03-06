import mysql.connector


class SQLStrQuery(object):
    def __init__(self, k, config):
        self.num_topics = k  # number of topics
        self.config = config  # config dict for database
        self.cnx = mysql.connector.connect(**config)  # Connect to SQL server
        self.cursor = self.cnx.cursor()  # Cursor to send queries

    def create_procedure(self):
        """Build the cosine similarity procedure based on the number of topics
        Returns: the query string that is a stored procedure
        """
        part1 = "CREATE PROCEDURE GetTopicCosDist(" + ','.join(
            [" IN B_Topic{0} INTEGER".format(i) for i in range(self.num_topics)]) + ") BEGIN \n"

        part2 = "DECLARE finished INTEGER DEFAULT 0; DECLARE Paper_Id INTEGER; DECLARE AB INTEGER; DECLARE A REAL; DECLARE B REAL; DECLARE CosDist REAL;" + ';'.join(
            [" DECLARE A_Topic{0} INTEGER".format(i) for i in range(self.num_topics)]) + ";\n"

        part3 = "DECLARE stdcur CURSOR FOR SELECT T.Paper_Id," + ','.join(["T.Topic{0}".format(i) for i in range(
            self.num_topics)]) + " FROM Topics_per_Paper T; DECLARE CONTINUE HANDLER FOR NOT FOUND SET finished = 1;\n"

        part4 = "DROP TABLE IF EXISTS temp_topic_table; CREATE TABLE temp_topic_table (Paper_Id INTEGER, CosineDistance REAL);  OPEN stdcur; REPEAT FETCH stdcur INTO Paper_Id," + ','.join(
            ["A_Topic{0}".format(i) for i in range(self.num_topics)]) + ";\n"

        part5 = "SET AB = " + ' + '.join(["A_Topic{0} * B_Topic{0}".format(i) for i in range(self.num_topics)]) + ";\n"

        part6 = "SET A = SQRT(" + '+'.join(
            ["A_Topic{0}".format(i) for i in range(self.num_topics)]) + "); SET B = SQRT(" + '+'.join(
            ["B_Topic{0}".format(i) for i in range(
                self.num_topics)]) + "); SET CosDist = ROUND(AB / (A * B), 2); INSERT INTO temp_topic_table VALUES (Paper_Id, CosDist)" + ";\n"

        part7 = "UNTIL finished END REPEAT; CLOSE stdcur; END"

        total_sql_str = part1 + part2 + part3 + part4 + part5 + part6 + part7

        return total_sql_str

    def create_tables(self):
        table_acad_journal = "CREATE TABLE Academic_Journal " \
                             "(Journal_Id INTEGER NOT NULL, Journal_Name CHAR(255), Category VARCHAR(1024), " \
                             "PRIMARY KEY(Journal_Id));"

        table_acad_paper = "CREATE TABLE Academic_Paper " \
                           "(Paper_Id INTEGER NOT NULL, Authors CHAR(64), Journal_Id INTEGER NOT NULL, Title CHAR(255), Abstract TEXT, " \
                           "PRIMARY KEY(Paper_Id), FOREIGN KEY(Journal_Id) REFERENCES Academic_Journal(Journal_Id));"

        topic_values = ["Paper_Id INTEGER NOT NULL"]
        for i in range(self.num_topics):
            topic_values.append("Topic{0} INTEGER".format(i))
        value_str = ",".join(topic_values)
        table_topic = "CREATE TABLE Topics_per_Paper (" + value_str + ", FOREIGN KEY(Paper_Id) REFERENCES Academic_Paper(Paper_Id));"

        return [table_acad_journal, table_acad_paper, table_topic]

    def construct_topic_vector(self, topic_indices):
        """ Construct the topic indicator vector
        Args:
            topic_indices:  List of topic indexes returned from LDA model
        Returns: indicator vector
        """
        value_str = ["0"] * self.num_topics
        for k in topic_indices:
            value_str[k - 1] = "1"
        return value_str

    def insert_journal(self):
        """ Insert Journal into Graph
        Returns: Query string
        """
        return "INSERT INTO Academic_Journal (Journal_Id, Journal_Name, Category) VALUES (%s, %s, %s);"

    def insert_paper(self):
        return "INSERT INTO Academic_Paper (Paper_Id, Authors, Journal_Id, Title, Abstract) VALUES (%s, %s, %s, %s, %s);"

    def update_paper(self, col_names):
        self.num_topics  # Not really required
        alter_str = ','.join([x + "=%s" for x in col_names])
        return "UPDATE Academic_Paper SET " + alter_str + " WHERE Paper_Id = %s;"

    def delete_paper(self):
        return "DELETE FROM Academic_Paper WHERE Paper_Id = %s;"

    def insert_topic(self, paper_id, topic_indices):
        """ Insert Paper-Topic Relationship into Graph
        Args:
            paper_id: the id of the paper inserted
            topic_indices: indicator topic vector
        Returns: Query string
        """
        topic_str = ','.join(["Topic{0}".format(i) for i in range(self.num_topics)])
        value_str = self.construct_topic_vector(topic_indices)
        value_str = ",".join(value_str)

        return "INSERT INTO Topics_per_Paper (Paper_Id, " + topic_str + ") VALUES (" + \
               str(paper_id) + "," + value_str + ");"

    def update_topic(self, topic_indices):
        value_str = self.construct_topic_vector(topic_indices)

        alter_str = ','.join(["Topic" + str(i) + "=" + value_str[i] for i in range(self.num_topics)])

        return "UPDATE Topics_per_Paper SET " + alter_str + " WHERE Paper_Id = %s;"

    def delete_topic(self):
        return "DELETE FROM Topics_per_Paper WHERE Paper_Id = %s;"

    def search_paper(self):
        return "SELECT * FROM Academic_Paper WHERE Paper_Id = %s;"

    def search_journal(self):
        return "SELECT * FROM Academic_Paper P JOIN Academic_Journal J ON P.Journal_Id=J.Journal_Id WHERE P.Journal_Id = %s;"

    def search_authors(self):
        return "SELECT * FROM Academic_Paper WHERE Authors LIKE \"%%s%\";"

    def get_recommended_papers(self, top_k):
        """ Get the top_k recommended papers ranked based on journal ranking and similarity
        Args:
            top_k: the top k papers
        Returns: Query string
        """
        if top_k < self.num_topics:
            top_k = self.num_topics
        return "SELECT P.Paper_Id, CosineDistance, P.Abstract, P.Authors, J.Journal_Id, P.Title FROM temp_topic_table T JOIN Academic_Paper P ON T.Paper_Id = P.Paper_Id JOIN Academic_Journal J ON P.Journal_Id=J.Journal_Id WHERE J.Rank!=0 ORDER BY CosineDistance DESC, J.Rank ASC LIMIT " + str(
            top_k) + ";"

    def execute_query(self, query_str, args=[], commit=True):
        """ Execute query on Neo4J graph
        Args:
            query_str: the query-string structure returned by the methods
            args: argument values to use in the query
            commit: Commit query or no
        Returns: (False, Error) or (True, Cursor)
        """
        try:
            self.cursor.execute(query_str, tuple(args))
        except Exception as e:
            # print("Error :" + str(e))
            return False, e
        if commit:
            self.cnx.commit()  # Queries that need to be commited

        return True, self.cursor

    def execute_topic_proc(self, topics):
        """ Run the stored procedure to calculate cosine similarity
        Args:
            topics: list of topic-tuples returned from LDA model
        Returns: (False, Error) or (True, Cursor)
        """
        try:
            self.cursor.callproc("GetTopicCosDist", args=tuple(self.construct_topic_vector(topics)))
        except Exception as e:
            print("Error :" + str(e))
            return False, e

        self.cnx.commit()  # Commit because we generate a temporary table

        return True, self.cursor

    def get_results(self, cursor_results):
        """ Parse results returned by the cursor of the database
        Args:
            cursor_results: Results returned by the cursor of this database
        Returns: list of values from cursor
        """
        parsed_results = []
        for row in cursor_results:
            parsed_results.append([str(x) for x in row])
        return parsed_results

    def close_db(self):
        """ Close database connection
        Returns: None
        """
        self.cursor.close()  # Close the cursor
        self.cnx.close()  # Close the server connection


if __name__ == '__main__':
    obj = SQLStrQuery(10)
    print(obj.create_procedure())
    # print(obj.update_paper([2, 4]))
    # obj.create_tables()
    # obj.insert_topic([2, 4])
